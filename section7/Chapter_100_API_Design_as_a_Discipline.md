# Chapter 100: API Design as a Discipline

> "An API is a contract with every engineer who will ever use it. Bad APIs cannot be fixed without breaking every caller. Good APIs are obvious to use correctly and hard to use incorrectly."

---

## Why This Chapter Exists

Every senior engineer has inherited a bad API. You know the feeling: the endpoint that returns 200 OK even when it fails, the field named `data` that sometimes contains an object and sometimes a list, the authentication scheme that requires three separate headers and a prayer, the `/doTheThing` endpoint that nobody knows what thing it does.

Bad APIs are forever. That is not an exaggeration. Once ten thousand clients are calling `GET /getUserInfo?id=123`, you cannot rename it to `GET /users/123`. Not without breaking every one of those clients. Not without coordination that, at scale, is essentially impossible.

This is what makes API design a discipline rather than just an implementation detail. It is one of the few engineering decisions that compounds. A good API makes every integration easier, every SDK smaller, every error recoverable. A bad API multiplies friction across every team, every partner, every year the system runs.

At L6, you are expected to design APIs that other engineers will build on for years. You are expected to identify API design mistakes before they get merged. And in system design interviews, you are expected to articulate *why* one API design is better than another — not just "I'd use REST" but specifically: here is the resource model, here are the status codes and what each means, here is how I handle pagination at scale, here is my versioning strategy and how I will sunset old versions.

This chapter is a complete treatment of API design as a professional discipline. It covers REST in depth, gRPC, GraphQL, versioning, error design, security, and developer experience. Read it, practice it, and use it to build APIs that your successors will thank you for.

---

## Part 1: APIs as Contracts — The Irreversibility Problem

### 1.1 What "Contract" Actually Means

When you publish an API — internal or external — you are making a promise. You are saying: "If you send me this request in this format, I will respond in this format, with this meaning." Every engineer who integrates with your API is trusting that promise.

The moment they ship code against your API, they have a dependency. And dependencies are sticky. They sit inside deployed services, inside mobile apps that users have not updated, inside third-party integrations you do not control.

This is the fundamental asymmetry of API design: making a breaking change is expensive, but making a backward-compatible one is free. So every design decision you make up front either preserves your future flexibility or eliminates it.

### 1.2 What "Breaking Change" Means

A breaking change is anything that causes existing clients to malfunction without any code change on their side.

**Breaking changes (the wall of pain):**
- Removing a field from a response
- Renaming a field (`user_id` → `userId`)
- Changing a field's type (`string` → `integer`)
- Changing a field's meaning (from user ID to session ID)
- Making a previously optional request field required
- Adding a new required request field
- Changing status codes (200 → 201, or 404 → 400)
- Changing authentication schemes
- Removing an endpoint
- Changing endpoint paths
- Changing HTTP method (GET → POST)

**Non-breaking changes (free):**
- Adding a new optional field to a response
- Adding a new optional request parameter
- Adding a new endpoint
- Adding new values to an enum (careful with strict parsers)
- Making a previously required field optional
- Adding a new status code for a new error condition

The discipline is knowing this list cold and designing your API so that the changes you will inevitably need are the non-breaking kind.

### 1.3 Internal vs External APIs: Different Stability Contracts

Not all APIs have the same cost of change. The key variable is: how much coordination does a change require?

```
INTERNAL API (same team, monorepo, same deploy)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cost to change: LOW
- You own both sides
- Can update caller and callee in same PR
- Breakage is caught in CI before it ships
- Coordinating one team is manageable

INTERNAL API (different teams, same company)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cost to change: MEDIUM
- You own the server, they own the client
- Must coordinate across team boundaries
- Deprecation notice → migration window → sunset
- Typical migration: weeks to months

EXTERNAL API (public, third-party developers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cost to change: VERY HIGH
- You own the server, they own the client
- Client may be mobile app, cannot force update
- Third parties may not even be responsive
- Deprecation notice → multi-year migration window
- Some clients never migrate (zombie clients)
- Stripe supports API versions from 2013 as of 2026
```

The practical implication: design your internal APIs with more care than you think you need to. That "internal" API between the payments service and the user service is internal until you have fifteen microservices calling it, at which point changing it costs weeks of coordination across three teams.

### 1.4 The Pit of Success

The "pit of success" principle comes from .NET framework design (Brad Abrams and Rico Mariani coined it). The idea is that APIs should be designed so that callers naturally fall into correct behavior without having to understand every detail.

The inverse — the "pit of failure" — is when correct use requires careful reading of documentation, special setup, or explicit handling that it is easy to forget.

**Pit of failure examples:**
```python
# WRONG: This API requires the caller to remember to close the resource
db = Database()
result = db.query("SELECT ...")
db.close()  # Easy to forget, especially in error paths
```

```python
# WRONG: This API silently ignores errors unless you check a return value
success = payment.charge(amount=100)
# What if success is False? Easy to forget to check.
```

**Pit of success examples:**
```python
# RIGHT: Context manager makes correct cleanup impossible to forget
with Database() as db:
    result = db.query("SELECT ...")
# close() is called automatically, even if an exception occurs
```

```python
# RIGHT: Raises an exception on failure, cannot be silently ignored
try:
    payment.charge(amount=100)
except PaymentDeclinedError as e:
    handle_decline(e)
```

In API design:
- Make authentication required and obvious, not optional and easy to forget
- Return errors loudly (non-2xx status codes), not silently in a 200 response body
- Name fields so their type is apparent (`user_id` not `user`, `amount_cents` not `amount`)
- Make idempotent operations idempotent by design, not by convention

### 1.5 Intern → Staff: Designing the Same Endpoint Four Ways

Let's say the product requirement is: "Create a new order for a user."

**Intern design:**
```
POST /createOrder
Body: { "userId": 123, "items": [...] }
Response: 200 OK with { "orderId": 456 }
```
Problems: verb in the URL (`createOrder`), no resource hierarchy, using 200 for creation (should be 201), no idempotency, will conflict with `GET /createOrder` if that is ever needed.

**Junior design:**
```
POST /orders
Body: { "user_id": 123, "items": [...] }
Response: 201 Created with { "id": 456, "status": "pending" }
```
Better: noun URL, correct status code, consistent naming. Missing: idempotency key, validation errors as proper 422, no Location header pointing to the created resource.

**Senior design:**
```
POST /v1/orders
Headers: Idempotency-Key: <uuid>
Body: {
  "user_id": "usr_123",
  "items": [
    { "product_id": "prod_456", "quantity": 2 }
  ],
  "currency": "USD"
}
Response 201:
{
  "id": "ord_789",
  "user_id": "usr_123",
  "status": "pending",
  "total_amount_cents": 4200,
  "created_at": "2026-06-20T10:00:00Z"
}
Headers: Location: /v1/orders/ord_789
```
Good: versioned, idempotent, string IDs with prefixes (easier to debug), amounts in cents (no floating point), ISO 8601 timestamps, Location header. Missing: what if the user does not exist? What if the product is out of stock? Need explicit 404 and 422 behaviors documented.

**Staff design:**
All of the above, plus:
- Documented failure modes: 404 if user not found, 422 with field-level validation errors if items invalid, 409 if idempotency key collision with different body, 429 with `Retry-After` header on rate limit
- Backward compatibility commitment: new optional fields will not break clients
- Observability contract: every response includes `X-Request-Id` for tracing
- Deprecation plan: when `v2` is ready, `v1` sunset schedule and migration guide
- Idempotency behavior explicitly documented: same key + same body = same order ID returned (idempotent), same key + different body = 409 Conflict

**The difference is not the happy path.** Every engineer can design the happy path. The difference is that staff engineers design the full contract including errors, edge cases, backward compatibility, and operational concerns — before any code is written.

---

### Part 1 Brainstorming Questions

**Q: At an interview, how do I know if an API is "internal" or "external" and why does it matter for my design?**

Almost always, you should ask: "Who are the clients of this API?" If the answer is your own team or other internal services, you have more flexibility to iterate. If the answer is third-party developers or mobile apps, you must treat the API as public from day one — because changing it later requires coordinating with people you do not control, across timelines you do not own.

In interviews, the safest move is to say: "I'll design this as a public API with full versioning and strict backward compatibility guarantees, since that's the harder problem and I can always relax constraints if we know it's internal-only." This shows maturity. Designing an external-quality API for an internal surface is almost never wrong; designing a loose internal-style API that later goes public is always painful.

The practical difference shows up in versioning (external APIs need explicit version contracts), deprecation timelines (external needs months to years, internal needs weeks), and error design (external clients need machine-readable errors and documentation links; internal clients can rely on shared knowledge).

**Q: Why is "make the right thing easy, the wrong thing hard" so hard to actually do?**

Because the designer knows how the API is supposed to be used. They do not feel the friction that an unfamiliar caller feels. This is called the "curse of knowledge" — you cannot un-know what you know. You have read the design doc, you wrote the implementation, you understand the edge cases. The caller has a Slack message saying "hey, try using our orders API" and fifteen minutes to figure it out.

The discipline is to force yourself to simulate being that caller. Write the integration code yourself before you finalize the design. See where you reach for the documentation. See what you have to look up. See what you get wrong on the first try. Every place you stumble is a place the API can be made more obvious.

The best teams also run "API usability testing" — sit a developer who has not been involved in the design down with the API spec and watch them try to build something. Do not explain anything. Take notes on every point of confusion. Then fix those points. This sounds expensive. It is a small fraction of the cost of shipping a confusing API that developers complain about for years.

**Q: What is the cost of being too conservative — making an API too stable when you could have been more flexible?**

Real cost: you carry forward design decisions that were wrong from the start, because you cannot fix them without breaking callers. Stripe, for example, committed to backward compatibility so aggressively that they still support API behaviors from 2013 that they now consider mistakes. Supporting old API versions has ongoing maintenance cost, documentation cost, and cognitive load for new engineers who have to understand why a legacy behavior exists.

The right calibration is: be conservative about the things that are hard to change (field names, types, meanings, endpoint paths, authentication schemes) and be liberal about the things that are easy to add later (new optional fields, new endpoints, new optional parameters). Stability of the core contract does not mean you cannot evolve the API — it means evolution happens through addition, not modification.

---

## Part 2: REST Design Done Right

### 2.1 Resources, Not Actions

REST stands for Representational State Transfer. The key word is "representational" — a REST API models things (resources) and transfers representations of their state. HTTP verbs (GET, POST, PUT, PATCH, DELETE) describe what you are doing to the resource. The URL names the resource.

The most common REST mistake is putting actions into URLs:

```
BAD API (verb-centric):
POST /createUser
POST /deleteUser
POST /getUserById
POST /updateUserEmail
GET  /searchUsers
POST /activateUser

GOOD API (resource-centric):
POST   /users           (create a user)
DELETE /users/{id}      (delete a user)
GET    /users/{id}      (get a user by ID)
PATCH  /users/{id}      (update a user's fields)
GET    /users?q=alice   (search users)
POST   /users/{id}/activate   (action on a sub-resource, acceptable)
```

The resource model makes the API predictable. If you know the pattern for users, you know the pattern for orders, for products, for anything. You do not have to learn each endpoint individually.

Sub-resources model relationships:

```
GET  /users/{user_id}/orders           (all orders for this user)
GET  /users/{user_id}/orders/{order_id} (specific order for this user)
POST /users/{user_id}/orders           (create order for this user)
```

Actions that do not fit neatly into CRUD use a noun sub-resource:

```
POST /payments/{id}/refund    (the "refund" noun represents the action)
POST /users/{id}/activate
POST /sessions                (login — creating a session is the action)
DELETE /sessions/{id}         (logout — deleting the session)
```

### 2.2 The Five Standard HTTP Methods

```
HTTP METHOD SEMANTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET     Read a resource or collection. SAFE (no side effects).
        IDEMPOTENT (calling twice = same result).
        Never use GET to trigger mutations.
        Cacheable by default.

POST    Create a new resource (or trigger an action).
        NOT safe (has side effects).
        NOT idempotent (calling twice may create two resources).
        Use idempotency keys when you need POST to be idempotent.

PUT     Replace a resource entirely.
        IDEMPOTENT (calling twice = same result as calling once).
        Sends the full representation of the resource.
        If field is missing from body, it gets cleared.

PATCH   Partially update a resource.
        NOT necessarily idempotent (depends on implementation).
        Sends only the fields that should change.
        More common than PUT in modern APIs.

DELETE  Remove a resource.
        IDEMPOTENT (deleting what is already gone = success).
        Usually returns 204 No Content.
        Some APIs return the deleted resource in body.
```

### 2.3 Status Code Semantics — Exactly What Each One Means

Status codes are part of the contract. Using them incorrectly breaks callers who make decisions based on them.

```
STATUS CODE REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2xx — SUCCESS (request succeeded)

200 OK
  Use for: GET requests that succeed, PATCH/PUT that succeed.
  Body: the resource or updated resource.
  Do NOT use for: creation (use 201). Do NOT use for errors.

201 Created
  Use for: POST requests that create a new resource.
  Body: the created resource.
  Headers: Location: /v1/orders/ord_789
  The Location header tells the caller where to find the resource.

202 Accepted
  Use for: async operations where work is queued, not yet done.
  Body: a reference (job ID, status URL) to check progress.
  Example: starting a long-running data export.

204 No Content
  Use for: DELETE that succeeds, or PATCH that returns nothing.
  Body: EMPTY. A 204 with a body is a contract violation.

4xx — CLIENT ERROR (the caller did something wrong)

400 Bad Request
  Use for: request is malformed, cannot parse JSON, missing
  required structure. The request is fundamentally broken.
  Do NOT use for: validation errors (use 422). For field-level
  problems, you should be more specific.

401 Unauthorized
  Use for: no credentials provided, or credentials are expired.
  The name is misleading — "Unauthorized" means "unauthenticated."
  Must include WWW-Authenticate header.
  The caller can fix this by authenticating.

403 Forbidden
  Use for: authenticated, but not allowed to do this action.
  The caller is known (authenticated) but cannot do what they asked.
  Example: reading another user's private data.
  Distinct from 401: the caller cannot fix this by re-authenticating.

404 Not Found
  Use for: the resource does not exist (or you don't want to
  reveal that it exists — use 404 instead of 403 for sensitive
  resources to avoid leaking existence information).
  Can also use for: unknown route (endpoint does not exist).

409 Conflict
  Use for: request is valid but conflicts with current state.
  Examples: creating a user with an email that already exists,
  idempotency key collision with a different body, optimistic
  locking failure (concurrent edit conflict).
  The caller can fix this by resolving the conflict.

410 Gone
  Use for: resource used to exist but has been permanently deleted.
  Stronger signal than 404 — search engines/clients know not to retry.

422 Unprocessable Entity
  Use for: request is syntactically valid but semantically invalid.
  Field-level validation errors: amount is negative, date is in
  the past, required field is empty.
  Body must contain field-level error details.
  This is the status code to use for "your data is wrong."

429 Too Many Requests
  Use for: rate limiting.
  Must include Retry-After header (seconds until retry is safe).
  May include X-RateLimit-Limit, X-RateLimit-Remaining headers.

5xx — SERVER ERROR (the server did something wrong)

500 Internal Server Error
  Use for: unexpected server errors. A bug. Something that should
  not have happened.
  The caller cannot fix this. They should retry with backoff.
  Never expose stack traces or internal details in the body.

502 Bad Gateway
  Use for: the server is a proxy and the upstream service failed.

503 Service Unavailable
  Use for: the service is temporarily down or overloaded.
  Include Retry-After header when possible.

504 Gateway Timeout
  Use for: upstream service timed out.
```

**The cardinal sin: returning 200 OK for errors.** Some APIs do this:

```json
BAD — DO NOT DO THIS:
HTTP/1.1 200 OK
{
  "success": false,
  "error": "User not found"
}
```

This breaks every HTTP client, monitoring tool, proxy, and load balancer in existence. They all assume 200 = success. You lose retry logic, alerting, circuit breakers — everything. Always use the correct HTTP status code.

### 2.4 What Goes Where: URL vs Query vs Body vs Headers

```
REQUEST ANATOMY GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL PATH — identifies the resource
  /v1/users/{user_id}/orders/{order_id}
  - Resource identity: what thing are we talking about?
  - Should be stable — part of the permalink to the resource
  - Do NOT put actions here (except for action sub-resources)
  - IDs belong here when getting a specific resource

QUERY PARAMETERS — filters, sorting, pagination, field selection
  /v1/orders?status=pending&sort=created_at&limit=20&cursor=xxx
  - Optional modifiers on a collection
  - Filtering: ?status=pending&user_id=usr_123
  - Sorting: ?sort=created_at&order=desc
  - Pagination: ?cursor=opaque_token&limit=20
  - Field selection: ?fields=id,status,total
  - Search: ?q=alice

REQUEST BODY — the resource representation (for POST/PUT/PATCH)
  { "amount_cents": 5000, "currency": "USD", "description": "..." }
  - Structured data: the thing you're creating or updating
  - Never put sensitive data (passwords, tokens) in query params
    (they show up in logs, referrer headers, browser history)
  - Use body for anything sensitive

HEADERS — cross-cutting concerns
  Authorization: Bearer <token>
  Idempotency-Key: <uuid>
  Content-Type: application/json
  Accept: application/json
  X-Request-Id: <uuid>
  - Authentication/authorization
  - Content negotiation
  - Idempotency
  - Tracing/correlation IDs
  - API version (if using header versioning)
  - Do NOT put business logic parameters in headers
  - Headers are for infrastructure concerns, not domain concerns
```

**Specific rules:**

1. Never put authentication tokens in URL paths or query params. They end up in server logs, proxy logs, browser history, and referrer headers. Always use the `Authorization` header.

2. Use `Content-Type: application/json` and `Accept: application/json` — be explicit about format.

3. Sensitive operations (create, update, delete) should never be GET requests. GET requests are logged, cached, prefetched by browsers.

4. Avoid deep nesting in URLs. Three levels is the max: `/v1/users/{id}/orders/{id}`. Beyond that, it is usually cleaner to query with a filter parameter.

### 2.5 Naming Conventions That Matter

Consistency is the most important thing in naming. Pick one convention and use it everywhere.

```
NAMING CONVENTION COMPARISON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

snake_case (Python/Ruby standard):
  user_id, created_at, total_amount_cents

camelCase (JavaScript/Java standard):
  userId, createdAt, totalAmountCents

Recommendation: snake_case for JSON APIs
  - More readable for multi-word fields
  - Language-neutral (no JS preference)
  - Standard in most successful API designs (Stripe, Twilio, GitHub)

FIELD NAMING RULES:
- Boolean: is_active, has_subscription, can_edit (not: active, subscription, edit)
- Timestamps: created_at, updated_at, deleted_at (ISO 8601)
- Monetary: amount_cents or amount (with currency field) — never floating point
- IDs: user_id, order_id, product_id — not just "id" in nested contexts
- Enums: lowercase snake: "status": "pending" not "PENDING" or "Pending"
- Collections: plural noun: "orders", "items", "users"
- Optional with absent vs null: use absent (omit the field) not null for not-applicable
```

---

### Part 2 Brainstorming Questions

**Q: When should I use PATCH vs PUT?**

Use PATCH almost always for update operations in modern REST APIs. PUT requires sending the full resource representation — if you leave a field out, it gets deleted or nulled. This is dangerous when resources have many fields and callers only know about some of them. A mobile app built against an older API version might not know about a new field, and if it PUTs the resource without that field, it silently deletes data.

PATCH sends only the fields that should change, making it safer for partial updates. The only case where PUT makes clear sense is when you truly want to replace the entire resource — for example, replacing a configuration file wholesale. In practice, 80% of "update" operations are better modeled as PATCH. When in doubt in an interview, use PATCH and explain that it is safer for partial updates.

**Q: When is it appropriate to use a 404 vs a 403?**

The HTTP spec says 403 Forbidden when the resource exists but the caller is not authorized to access it. However, returning 403 leaks information: you are telling the caller that the resource exists (they just cannot see it). For security-sensitive resources — think: does user A know that user B has a certain medical record? — returning 404 for resources the caller cannot access prevents information leakage through the existence check.

The rule of thumb: if knowing that a resource exists is itself sensitive information, use 404 for both "not found" and "not authorized." If the existence of the resource is not sensitive (e.g., public articles, products), use 403 for "exists but not authorized" so the caller knows they need to get authorization rather than thinking the resource does not exist. In payment or healthcare APIs, almost always use 404. In general-purpose APIs, use 403 when you want to help the caller understand they need to get access.

**Q: I've seen APIs that return different shapes for the same endpoint depending on parameters. Is that OK?**

It is a significant design smell. When the same endpoint returns structurally different responses depending on query parameters or caller state, clients have to handle multiple cases in a single code path — it multiplies complexity and bugs. Every distinct shape should ideally be a distinct endpoint.

If you find yourself designing an endpoint that "returns user data if type=user and order data if type=order," stop and make two endpoints: `/users/{id}` and `/orders/{id}`. The one exception where shape polymorphism is sometimes acceptable is field selection (`?fields=id,name`), but even that should be additive — you are returning a subset of a fixed shape, not a fundamentally different structure. In interviews, if you catch yourself designing an endpoint with multiple return shapes, that is a signal to refactor the resource model.

---

## Part 3: Pagination, Filtering, and Field Selection

### 3.1 Why Pagination Is Not Optional

Any endpoint that returns a collection must be paginated. Full stop. The reason is scale: today there are 100 orders, so you return all 100. Next year there are 10 million. Now the response is gigabytes of JSON, the database query takes minutes, and every caller crashes.

Pagination is a forward compatibility requirement. You cannot add mandatory pagination to a collection endpoint without breaking every caller who assumed they got all the data.

### 3.2 Offset Pagination — Simple But Broken at Scale

Offset pagination is what most people implement first because it maps directly to SQL:

```sql
SELECT * FROM orders LIMIT 20 OFFSET 40;
```

The API looks like:
```
GET /v1/orders?limit=20&page=3
or
GET /v1/orders?limit=20&offset=40
```

**The problem:** Offset pagination is fundamentally broken at scale.

```
OFFSET PAGINATION PROBLEM: PHANTOM READS AND SKIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Client fetches page 1 (orders 1-20):
[Order 1, Order 2, ..., Order 20]

While client is processing page 1, someone inserts a new order
at the beginning (newer timestamp, sorts to position 1):
[NEW ORDER, Order 1, Order 2, ..., Order 20, Order 21, ...]

Client fetches page 2 (offset=20):
[Order 21, Order 22, ..., Order 40]

Client SKIPPED Order 20 entirely.
Client would also see Order 20 AGAIN if they paginate backward.

Also: COUNT(*) for total pages is expensive at scale.
Database must scan the full index to compute total pages.
At 100M rows, this is O(n) and kills performance.
```

Additionally, the database has to scan and discard all rows up to the offset. `OFFSET 1000000` is a table scan of 1 million rows that you throw away.

### 3.3 Cursor Pagination — The Right Answer at Scale

```
CURSOR PAGINATION MECHANICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Request page 1:
  GET /v1/orders?limit=20&sort=created_at_desc

Response:
{
  "data": [...20 orders...],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6Im9yZF84NzYiLCJjcmVhdGVkX2F0IjoiMjAyNi0wNi0yMFQwOTowMDowMFoifQ"
  }
}

Request page 2:
  GET /v1/orders?limit=20&sort=created_at_desc&cursor=eyJpZCI6Im9yZF84NzYi...

Server decodes cursor: { "id": "ord_876", "created_at": "2026-06-20T09:00:00Z" }
Server runs:
  SELECT * FROM orders
  WHERE (created_at, id) < ('2026-06-20T09:00:00Z', 'ord_876')
  ORDER BY created_at DESC, id DESC
  LIMIT 20;
```

The cursor is an opaque token — the client does not parse it, just passes it back. Internally it encodes the position in the result set (usually the sort key values of the last item on the previous page).

**Why cursor wins:**
1. No phantom reads or skips — anchored to a specific row, not a position number
2. Constant-time database query — no full index scan
3. Works correctly with concurrent inserts/deletes
4. Scales to billions of rows

**Why offset is still used:**
1. Users want to jump to page 50 — cursors do not support random access
2. "Total count" is needed for a progress indicator — cursors do not provide total count
3. Simple for developers to understand

**In an interview:** use cursor pagination for any high-scale collection endpoint (feeds, event streams, large datasets). Use offset for admin tools or anywhere users need to jump to arbitrary pages. Be explicit about this trade-off.

### 3.4 Implementing Cursor Pagination Correctly

The cursor must include all fields in the `ORDER BY` clause, plus the primary key as a tiebreaker to ensure stable ordering when sort fields have duplicates.

```python
# Server-side cursor encoding
import base64
import json

def encode_cursor(order: Order) -> str:
    payload = {
        "created_at": order.created_at.isoformat(),
        "id": order.id
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str) -> dict:
    return json.loads(base64.b64decode(cursor).encode())

# Database query using cursor
def get_orders(cursor: str | None, limit: int) -> list[Order]:
    query = "SELECT * FROM orders"
    if cursor:
        position = decode_cursor(cursor)
        query += f"""
            WHERE (created_at, id) < (
                '{position["created_at"]}',
                '{position["id"]}'
            )
        """
    query += f" ORDER BY created_at DESC, id DESC LIMIT {limit + 1}"
    # Fetch limit+1 to know if there is a next page
    rows = db.execute(query)
    has_more = len(rows) > limit
    return rows[:limit], has_more
```

### 3.5 Filtering and Sorting

```
FILTERING PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Simple equality:
  GET /v1/orders?status=pending

Multiple values (OR):
  GET /v1/orders?status=pending,shipped
  or: GET /v1/orders?status[]=pending&status[]=shipped

Range:
  GET /v1/orders?created_at[gte]=2026-01-01&created_at[lte]=2026-06-01
  (Stripe uses this syntax — clear and unambiguous)

Full text search:
  GET /v1/users?q=alice

Nested field filter:
  GET /v1/orders?user.country=US

SORTING PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Single field:
  GET /v1/orders?sort=created_at&order=desc

Multiple fields:
  GET /v1/orders?sort=status,-created_at  (- prefix = descending)

Always define a default sort and document it. Never return results
in undefined order — it makes pagination non-deterministic.
```

### 3.6 Field Selection

Field selection lets callers request only the fields they need, reducing response size and bandwidth.

```
GET /v1/users?fields=id,email,created_at

Response:
{
  "data": [
    { "id": "usr_123", "email": "alice@example.com", "created_at": "..." }
  ]
}
```

This is especially important for mobile clients where bandwidth is expensive. GraphQL formalizes this into the query language. In REST, it is a convention.

When implementing field selection:
- Always include `id` even if not requested (makes no sense to return a row with no identifier)
- Document which fields are always returned vs selectable
- Consider default field sets vs full field sets (`?fields=full` for everything)

---

### Part 3 Brainstorming Questions

**Q: A product manager wants to show "Page 5 of 23" pagination in the UI. Should I support total counts in my cursor-based pagination API?**

This is a real tension. Cursor pagination does not naturally provide a total count because computing the count requires scanning the full index. At 100M rows, that is an expensive query you do not want on every page load.

The practical resolution: provide a separate count endpoint (`GET /v1/orders/count`) that can be cached aggressively (it does not need to be exact — "~23 pages" is fine for most UIs). Alternatively, do the count query asynchronously and cache it for a short TTL (e.g., 60 seconds). The UI shows an approximate count that refreshes occasionally, which is usually acceptable.

In some cases the right answer is: do not show total pages. Many modern UIs (Twitter, Instagram, Google Search on mobile) use infinite scroll, which maps directly to cursor pagination with no total count. The "page X of Y" pattern comes from the desktop web era and is increasingly rare in high-scale systems. In an interview, point out this trade-off explicitly — it shows you understand that API design and product design interact.

**Q: How do I handle a caller that passes a cursor from an old API version in a new API version?**

This is a real operational headache. Cursors encode internal state (sort keys, row positions) that can change between API versions. If the sort order changes or the table structure changes, old cursors become invalid.

The defensive answer: cursors should be treated as opaque and short-lived. Document a cursor TTL (e.g., 24 hours) after which they expire. When a cursor is invalid or expired, return a 400 with a clear error: `{ "error": { "code": "invalid_cursor", "message": "Cursor has expired or is invalid. Please start pagination from the beginning." } }`. Do not try to be clever about backward-compatible cursor decoding across versions — it creates subtle bugs and complicated migration logic. Make the failure explicit and recoverable (caller can restart pagination from the first page).

**Q: What is the difference between a filter and a search, and why does it matter for API design?**

Filters are equality/range operations on indexed fields: `status=pending`, `created_at>=2026-01-01`. These map cleanly to database queries and are performant.

Search (`?q=alice`) is full-text search — matching against text fields, possibly across multiple columns, with ranking and relevance. This is typically backed by Elasticsearch or a similar full-text search engine, not the primary database.

They are different data access patterns that often require different backends. The API design implication: keep them separate if they have different performance characteristics. It is fine to have both `GET /users?email=alice@example.com` (indexed filter) and `GET /users?q=alice` (full-text search). Do not pretend they are the same — full-text search is expensive, eventually consistent with the primary database, and may have different result ordering semantics. Make callers aware of these differences through documentation.

---

## Part 4: Idempotency — The Safety Net for Critical Operations

### 4.1 Why Idempotency Matters for Financial APIs

Networks fail. Requests time out. Clients retry. Without idempotency, retries cause duplicate operations. In a payment system, that means charging a customer twice. In an order system, that means placing the same order twice. In a messaging system, that means sending the same message twice.

Idempotency is the guarantee that performing the same operation multiple times has the same effect as performing it once.

**The problem without idempotency:**
```
Client                    Server                    Database
  |                          |                          |
  |--- POST /payments ------->|                          |
  |                          |--- INSERT payment ------->|
  |                          |<-- success ---------------|
  |                          |                          |
  |  (network timeout)       |                          |
  |  (client never sees      |                          |
  |   the response)          |                          |
  |                          |                          |
  |--- POST /payments ------->|  (retry)                 |
  |                          |--- INSERT payment ------->|  DUPLICATE!
  |                          |<-- success ---------------|
  |<-- success --------------|
```

### 4.2 Idempotency Keys — How Stripe Does It

Stripe's idempotency key pattern is the gold standard. The client generates a unique key per logical operation (usually a UUID) and includes it in the `Idempotency-Key` header. The server stores the key and, on subsequent requests with the same key, returns the original response instead of re-executing the operation.

```
STRIPE IDEMPOTENCY KEY FLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

First request:
  POST /v1/charges
  Idempotency-Key: 7f1e2b3c-4d5e-6f7a-8b9c-0d1e2f3a4b5c
  { "amount": 5000, "currency": "usd", "source": "tok_visa" }

Server:
  1. Check idempotency store: key not seen before
  2. Execute the charge: charge_id = ch_abc123
  3. Store: key → { status: 200, body: {...charge...}, charge_id: "ch_abc123" }
  4. Return 200 with the charge object

Network timeout — client retries:
  POST /v1/charges
  Idempotency-Key: 7f1e2b3c-4d5e-6f7a-8b9c-0d1e2f3a4b5c  (same key)
  { "amount": 5000, "currency": "usd", "source": "tok_visa" }

Server:
  1. Check idempotency store: key SEEN before
  2. Return the STORED response — no new charge
  3. Same 200, same charge object, same charge_id

Result: client gets success, no duplicate charge.
```

**Edge case: same key, different body.** This is a programming error — the client generated the same UUID for two different operations. Stripe returns 409 Conflict: "Idempotency key `xxx` already used with different request parameters."

**Implementation details:**
- Store idempotency keys in a fast store (Redis works well)
- TTL: Stripe stores keys for 24 hours, which matches retry window expectations
- The stored value is: key → (response_status, response_body, operation_result_id)
- Concurrent requests with the same key: first one wins, second waits for first to complete, then returns stored response

**When to require idempotency keys:**
- Any POST that creates a financial record (charges, payments, refunds)
- Any POST that sends an irreversible external action (email, SMS, webhook)
- Any operation where duplication is harmful
- Make it mandatory for critical endpoints, not optional

```
BAD: Idempotency-Key is optional and easy to forget
  POST /v1/payments
  (Idempotency-Key header is optional)

GOOD: Idempotency-Key is required for this endpoint
  POST /v1/payments
  Idempotency-Key: <required, 422 if missing>
```

### 4.3 Designing Naturally Idempotent Operations

Not every operation needs an idempotency key. Some operations are naturally idempotent:

- **GET**: reading the same resource twice returns the same data. Always safe to retry.
- **PUT**: replacing a resource with the same content leaves it in the same state.
- **DELETE**: deleting something that is already gone. The convention is to return 200 or 204 (not 404) on a re-delete, since the end state is the same.

Operations that are NOT naturally idempotent and need explicit handling:
- **POST to create**: creates a new thing each time. Need idempotency key or a unique constraint.
- **POST to increment**: "add 10 to the balance." Calling twice adds 20. Need idempotency key.
- **Any operation with external side effects**: sending an email, charging a card.

### 4.4 Database-Level Idempotency

For some operations, you can use the database itself to enforce idempotency:

```sql
-- Unique constraint prevents duplicate records
CREATE UNIQUE INDEX idx_charges_idempotency_key 
  ON charges(idempotency_key);

-- Insert or return existing
INSERT INTO charges (idempotency_key, amount, user_id)
VALUES ('7f1e2b3c...', 5000, 'usr_123')
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING *;
-- If conflict, SELECT the existing row and return it
```

This pattern moves idempotency enforcement into the database, which is simpler but does not handle external side effects (the charge to Stripe might have gone through before the database insert failed).

---

### Part 4 Brainstorming Questions

**Q: How do I handle idempotency for operations that have external side effects, like sending an email or calling a third-party payment processor?**

This is the hardest case. The sequence is: (1) call external service, (2) record locally. If step 1 succeeds and step 2 fails, you have charged the card but have no record. If step 1 fails and you retry, you might charge twice.

The Stripe approach: first record the intent ("pending charge"), then execute the external call, then update the record to reflect the result. The idempotency store gates the whole operation. If a retry comes in while the first request is still in-flight (pending state), the server holds the retry request until the first request completes, then returns the stored result. This requires careful locking but guarantees exactly-once semantics from the client's perspective.

The simpler approach for less critical operations: include a unique external reference ID in the call to the third party (most payment processors support this — Stripe calls it `idempotency_key` on their end too). If you retry the external call, they deduplicate it. Then your local state is a simple "did we get a success back from the external service?" check. This pushes the idempotency problem to the downstream service rather than solving it yourself.

**Q: What should I return when an idempotent request comes in after the original operation failed — do I return the original error or try again?**

Stripe's answer: return the original error. If the first request returned 402 Payment Required (card declined), a retry with the same idempotency key returns the same 402. The caller needs to use a different idempotency key if they want to try again (e.g., with a different payment method).

This is the right answer because the idempotency key represents "this specific attempt." If the attempt failed, the caller needs to acknowledge that and start a new attempt. The alternative — retrying on errors — would mean the idempotency key store is useless for failed operations, and callers could accidentally trigger retries when they just want to know the status of the original attempt.

The practical implication for your implementation: store the full response (including error responses) in the idempotency store, not just successful responses. The stored response is replayed regardless of success or failure.

**Q: How long should idempotency keys be stored?**

This depends on your retry window. Stripe stores them for 24 hours. The reasoning: most retry logic uses exponential backoff with a maximum retry window of a few hours. 24 hours is generous enough that any reasonable retry would still be within the window.

Too short (e.g., 5 minutes): network partitions or slow database failovers could outlast the window, causing duplicates after the window expires. Too long (e.g., 1 year): your idempotency store grows unbounded, and you pay storage costs for stale keys. The sweet spot is 24 to 48 hours — long enough for any realistic retry scenario, short enough to contain storage growth with a simple TTL sweep.

---

## Part 5: gRPC and Protocol Buffers

### 5.1 When gRPC is Better Than REST

gRPC is a high-performance RPC framework that uses Protocol Buffers (protobuf) as its serialization format and HTTP/2 as its transport. It is the standard for service-to-service communication at companies like Google, Netflix, and Uber.

```
gRPC vs REST COMPARISON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Feature             REST (JSON/HTTP/1.1)      gRPC (protobuf/HTTP/2)
─────────────────────────────────────────────────────────────────────
Serialization       JSON (text, large)         Binary (small, fast)
Schema              Optional (OpenAPI)         Required (.proto file)
Code generation     Optional                   Built-in
Type safety         Optional                   Enforced at compile time
Streaming           Awkward (SSE/WebSocket)    Built-in (4 patterns)
Browser support     Native                     Requires grpc-web proxy
Human readable      Yes (JSON)                 No (binary)
Contract strictness Loose (schema optional)    Strict (proto required)
Performance         Good                       Excellent (~3-10x faster)
Versioning          URL or header              Proto field numbers
Interoperability    Universal                  Needs gRPC stub
─────────────────────────────────────────────────────────────────────

CHOOSE gRPC WHEN:
- Internal service-to-service calls where performance matters
- Streaming data (real-time events, log streams, video, chat)
- Strict contract enforcement between teams (compile-time type checking)
- Polyglot environment (gRPC generates stubs for 10+ languages)
- Latency-sensitive paths (payment processing, recommendation engine)

CHOOSE REST WHEN:
- Public APIs consumed by third-party developers (browser-native)
- Simple CRUD where performance is not the bottleneck
- Teams that are not set up for proto toolchain
- Caching matters (HTTP caching works natively with REST+GET)
- You need human-readable requests/responses for debugging
```

### 5.2 Protocol Buffer Design

A `.proto` file defines the contract between services. It is the schema — the thing both sides agree on.

```protobuf
// orders.proto

syntax = "proto3";

package orders.v1;

option go_package = "github.com/company/orders/api/v1";

// Good: descriptive names, explicit field numbers, snake_case
message Order {
  string id = 1;
  string user_id = 2;
  OrderStatus status = 3;
  int64 total_amount_cents = 4;    // Always use int64 for money
  string currency_code = 5;       // ISO 4217: "USD", "EUR"
  google.protobuf.Timestamp created_at = 6;  // Use well-known types
  repeated OrderItem items = 7;
  // Field 8 reserved for future use
}

message OrderItem {
  string product_id = 1;
  int32 quantity = 2;
  int64 unit_price_cents = 3;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;   // Always have a 0/unspecified value
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_SHIPPED = 3;
  ORDER_STATUS_DELIVERED = 4;
  ORDER_STATUS_CANCELLED = 5;
}

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
  rpc GetOrder(GetOrderRequest) returns (Order);
  rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
  rpc StreamOrderUpdates(StreamOrderUpdatesRequest) returns (stream OrderUpdate);
}

message CreateOrderRequest {
  string user_id = 1;
  repeated OrderItem items = 2;
  string idempotency_key = 3;     // Idempotency still matters in gRPC
}

message CreateOrderResponse {
  Order order = 1;
}
```

### 5.3 Backward Compatibility Rules in Protobuf

This is the most important section for senior engineers working with gRPC. Protobuf uses field numbers (not names) to encode data. This is what makes backward compatibility possible — and also what makes certain changes dangerous.

```
WHAT YOU CAN DO (backward compatible):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ADD a new field with a new field number:
  message Order {
    string id = 1;
    // ... existing fields ...
    string shipping_address = 9;  // NEW — old clients ignore it
  }

ADD a new RPC method:
  service OrderService {
    rpc CreateOrder(...) returns (...);
    rpc CancelOrder(...) returns (...);  // NEW — old clients don't call it
  }

RENAME a field:
  The name is not part of the wire format. Only the number matters.
  string user_id = 2;  can be renamed to  string customer_id = 2;
  Old clients will still decode field 2 correctly.
  WARNING: If you generate code from the proto, renaming breaks
  generated code — treat this as a code-level breaking change even
  though the wire format is compatible.

WHAT YOU CANNOT DO (breaking):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REUSE a field number for a different type:
  // BEFORE: string user_id = 2;
  // AFTER:  int64 user_id = 2;   BROKEN — old clients decode as string
  // AFTER:  string order_id = 2; BROKEN — semantic mismatch, same encoding

REMOVE a field (without reserving the number):
  If you remove field 4, and later add a new field 4 with a different
  type, old clients will misinterpret the data.
  CORRECT: Reserve the number:
  message Order {
    reserved 4;        // Do not reuse this number
    reserved "legacy_field_name";  // Do not reuse this name
  }

CHANGE a field from singular to repeated (or vice versa):
  string status = 3;     →    repeated string statuses = 3;
  Wire format is completely different. Breaks old clients.

CHANGE enum values:
  Removing an enum value or changing its number breaks old clients
  that encounter data with the old value.
```

### 5.4 The Four Streaming Patterns

HTTP/2, which gRPC runs on, supports multiplexed streaming that HTTP/1.1 cannot do efficiently.

```
gRPC STREAMING PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. UNARY (request → response)
   rpc GetOrder(GetOrderRequest) returns (Order);
   One request, one response. Standard RPC.
   Use for: most operations (CRUD).

2. SERVER STREAMING (request → stream of responses)
   rpc StreamOrderUpdates(StreamOrderUpdatesRequest) returns (stream OrderUpdate);
   One request, server sends many responses over time.
   Use for: real-time updates, feed subscriptions, log tailing,
   progress updates on long operations.

3. CLIENT STREAMING (stream of requests → response)
   rpc UploadOrderItems(stream OrderItem) returns (BatchUploadResponse);
   Client sends many messages, server responds once.
   Use for: batch uploads, streaming sensor data, large file upload.

4. BIDIRECTIONAL STREAMING (stream ↔ stream)
   rpc Chat(stream ChatMessage) returns (stream ChatMessage);
   Both sides send many messages independently.
   Use for: real-time chat, collaborative editing, live game state.

Code example (Go, server streaming):
  // Server
  func (s *OrderServer) StreamOrderUpdates(req *pb.StreamOrderUpdatesRequest,
      stream pb.OrderService_StreamOrderUpdatesServer) error {
      for update := range s.orderUpdates {
          if err := stream.Send(update); err != nil {
              return err  // Client disconnected
          }
      }
      return nil
  }

  // Client
  stream, _ := client.StreamOrderUpdates(ctx, req)
  for {
      update, err := stream.Recv()
      if err == io.EOF { break }
      if err != nil { log.Fatal(err) }
      process(update)
  }
```

---

### Part 5 Brainstorming Questions

**Q: Our team is moving from REST to gRPC for internal services. What are the migration pitfalls?**

The biggest pitfall is treating gRPC as "just REST with binary encoding." gRPC has different operational characteristics that your team needs to be prepared for. Debugging is harder — you cannot just `curl` a gRPC endpoint and read JSON. You need tools like `grpcurl` or `grpc_cli`. Load balancers need to understand HTTP/2 properly (L4 load balancers like many AWS ELBs do not work correctly with gRPC streaming — you need an HTTP/2-aware L7 load balancer). Timeouts work differently in gRPC (they are client-set deadlines propagated to the server via `grpc-timeout` header). Error handling uses gRPC status codes (NOT HTTP status codes) which your monitoring and alerting need to handle.

The migration strategy that works: run both REST and gRPC in parallel during transition. Add a gRPC interface alongside the existing REST interface (use a gRPC gateway or a shared handler). Migrate services one at a time, validating each migration. Do not attempt a big-bang migration from REST to gRPC — the operational and debugging differences will bite you at the worst time.

**Q: How do gRPC errors work and how do they compare to HTTP status codes?**

gRPC has its own set of status codes completely separate from HTTP: OK (0), CANCELLED (1), UNKNOWN (2), INVALID_ARGUMENT (3), NOT_FOUND (5), ALREADY_EXISTS (6), PERMISSION_DENIED (7), RESOURCE_EXHAUSTED (8), FAILED_PRECONDITION (9), ABORTED (10), UNAVAILABLE (14), DEADLINE_EXCEEDED (4), INTERNAL (13), and more. These roughly map to HTTP status codes but are not identical.

For rich error details (field-level validation errors, retry hints, localized messages), gRPC has the `google.rpc.Status` proto and the error details proto extensions (`google.rpc.BadRequest`, `google.rpc.ErrorInfo`, `google.rpc.RetryInfo`). These let you attach structured error information similar to what you would put in a JSON error body. The key discipline: do not just return `INTERNAL` for everything that fails — use the most specific status code, and attach `google.rpc.Status` details for client-actionable information. The same philosophy as good REST error design applies: help the caller understand what went wrong and how to fix it.

---

## Part 6: GraphQL — Real Advantages and Real Costs

### 6.1 What GraphQL Actually Solves

GraphQL was invented at Facebook in 2012 to solve a specific problem: their mobile app needed wildly different data shapes for different screens, and they were drowning in REST endpoints that each returned more than any one screen needed.

The core idea: the client declares exactly what data it needs, and the server returns exactly that — nothing more, nothing less.

```graphql
# Client asks for exactly what the news feed screen needs
query NewsFeed {
  me {
    id
    name
    feedPosts(first: 10) {
      edges {
        node {
          id
          text
          createdAt
          author {
            id
            name
            avatarUrl
          }
          likeCount
          commentCount
        }
      }
    }
  }
}
```

Without GraphQL, this might require: `GET /me`, `GET /me/feed`, `GET /users/{id}` for each post's author — potentially dozens of requests or a custom `GET /feed/summary` endpoint that only one screen uses.

### 6.2 The Real Advantages

**No overfetch:** A REST endpoint for user profiles might return 50 fields. A mobile screen needs 4 of them. GraphQL returns only the 4.

**No underfetch:** No N+1 REST calls. One GraphQL query can fetch a user + their orders + each order's items in a single round trip.

**Typed schema:** The GraphQL schema is a contract. Clients can introspect it, IDEs autocomplete it, tools validate it.

**Client-driven evolution:** Adding a new field to the schema does not break existing queries (they just do not request it). The schema evolves without versioning ceremonies.

**The BFF pattern (Backend for Frontend):** A GraphQL layer sits between clients and internal services, translating client-specific queries into calls to REST or gRPC services. The BFF can be owned by the frontend team, giving them control over their data contract without touching backend services.

```
BFF PATTERN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mobile App ──→ GraphQL BFF ──→ UserService (gRPC)
Web App    ──→ GraphQL BFF ──→ OrderService (REST)
           (same BFF)      ──→ ProductService (REST)
                           ──→ NotificationService (gRPC)

The BFF:
- Aggregates data from multiple services per client query
- Understands client-specific data shapes
- Handles schema evolution without coordinating with each backend
- Frontend team owns it, so no cross-team negotiation for new fields
```

### 6.3 The Real Costs

GraphQL is not a free lunch. The advantages come with serious operational costs.

**The N+1 Problem:**
```graphql
# This query looks innocent:
query {
  orders(first: 100) {
    id
    user {
      name  # For each of 100 orders, we need to load 1 user
    }
  }
}

# Naive implementation:
# 1 query for orders
# 100 queries for users (one per order)
# = 101 queries total
# This is the N+1 problem
```

The fix is DataLoader (batching and caching) — for each type that gets fetched inside a list, you collect all the IDs from the list and make one batched query. This is extra work that REST does not require.

**Caching is hard:** REST has HTTP caching built in — `Cache-Control`, `ETag`, `Vary` headers all work automatically. GraphQL queries are POST requests, which HTTP does not cache. You need application-level caching (per-field caching, persisted queries, CDN query caching). This is significantly more complex to set up correctly.

**Security surface is larger:** GraphQL's flexibility means callers can compose arbitrarily complex queries:
```graphql
# Abusive query:
query {
  user(id: "usr_1") {
    orders {
      items {
        reviews {
          author {
            orders {  # Deeply nested — exponential database load
              items {
                reviews { ... }
              }
            }
          }
        }
      }
    }
  }
}
```
You need query depth limits, query complexity analysis, and cost estimation to prevent this. REST endpoints do not have this problem — each endpoint has a fixed cost.

**Harder to evolve:** Removing a field from GraphQL requires deprecating it (marking `@deprecated`) and waiting until all clients stop using it. With REST, you can version the endpoint. With GraphQL, the schema is shared across all clients.

### 6.4 When to Choose GraphQL vs REST

```
DECISION TREE: REST vs GraphQL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Is this a public API?
  → YES → REST (public APIs work better with REST; GraphQL security complexity is hard for third parties)

Do you have many different clients (mobile, web, TV) needing different data shapes?
  → YES → GraphQL BFF worth the complexity

Is caching critical (high read volume, CDN caching, browser caching)?
  → YES → REST (HTTP caching is automatic)

Do clients need to compose queries on the fly (dashboards, analytics)?
  → YES → GraphQL (it is designed for this)

Is this simple CRUD?
  → YES → REST (no need for GraphQL complexity)

Are you a small team without DataLoader/security expertise?
  → REST (GraphQL operational overhead is real)

Do you have highly relational data that varies per client?
  → YES → GraphQL is genuinely better
```

---

### Part 6 Brainstorming Questions

**Q: In an interview, if I propose GraphQL, will the interviewer think I am just throwing buzzwords?**

Only if you cannot defend the trade-offs. If you say "GraphQL for type safety and client-driven queries," and the interviewer asks "what about the N+1 problem?" and you stare blankly, that is a red flag. If you say "GraphQL is a good fit because we have a mobile and a web client needing different data shapes, but I would need to implement DataLoader for batching and set up query cost limits to prevent abuse," that shows you understand the real costs.

The rule: do not propose a technology you cannot operate. GraphQL requires DataLoader, query depth limits, query complexity analysis, and a caching strategy that works without HTTP caching. If you can describe those, propose GraphQL when it fits. If you cannot, propose REST and explain why its simplicity and cacheability are advantages for this use case. Interviewers value accurate assessment of trade-offs over buzzword knowledge.

**Q: How do you handle authorization in GraphQL? It seems harder than REST.**

In REST, authorization is per-endpoint: "Can this user call GET /orders/{id}?" In GraphQL, authorization is per-field because the same query can access fields from multiple resources: "Can this user see the `salary` field on a `User`? Can they see a different user's `orders`?"

The two main approaches: (1) field-level resolvers check authorization themselves — each resolver that touches sensitive data calls an authorization service. This is verbose but correct. (2) Use a library like `graphql-shield` that lets you define authorization rules as a layer on top of the schema.

The critical mistake is putting authorization only at the query entry point. If you check "can this user run queries?" but not "can this user see this specific field?", you will have horizontal privilege escalation bugs where a user can see data belonging to other users by constructing the right query. Always authorize at the field or resolver level, not just at the HTTP gateway.

---

## Part 7: API Versioning — The Long Game

### 7.1 The Three Versioning Strategies

```
API VERSIONING STRATEGY TIMELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRATEGY 1: URL VERSIONING
  /v1/orders    /v2/orders    /v3/orders
  
  Advantages:
  - Immediately obvious which version you're using
  - Easy to route in load balancers (path-based routing)
  - Easy to test: just change the URL
  - No hidden headers required
  
  Disadvantages:
  - Version is in the URL, which REST purists argue breaks
    the "URL identifies a resource" principle
  - Clients must update URL to upgrade (mechanical change)
  - Deprecation requires supporting multiple URL prefixes
  
  Used by: Stripe (/v1/), AWS services (/2013-11-01/),
           GitHub (/v3/), Twilio (/2010-04-01/)

STRATEGY 2: HEADER VERSIONING
  GET /orders
  Accept: application/vnd.myapp.v2+json
  or: API-Version: 2026-06-01
  
  Advantages:
  - "Clean" URLs — the resource URL does not change
  - Can negotiate version per-request
  
  Disadvantages:
  - Invisible — hard to see which version is being called
  - Cannot bookmark or share versioned URLs
  - Browser cannot use natively
  - Load balancer routing by header is more complex
  
  Used by: GitHub API (GraphQL endpoint), some internal APIs

STRATEGY 3: DATE-BASED VERSIONING (Stripe's model)
  Stripe-Version: 2024-09-30
  
  Each API version is a date. New behaviors ship as new version dates.
  Customers "lock in" to the version they tested against.
  Old versions are supported indefinitely (Stripe policy).
  
  Advantages:
  - Granular: versions correspond to specific changes, not big rewrites
  - Customers can opt in to new behaviors on their own schedule
  - No big-bang "v2" migrations
  
  Disadvantages:
  - Complexity: supporting 50+ version dates simultaneously
  - Code is riddled with version checks
  - Requires discipline and significant investment in testing

STRATEGY 4: NO VERSIONING (backward compatible only)
  Never break. All changes are additive.
  "The URL is the permanent name of the resource."
  
  Works until it does not.
  When you genuinely need a breaking change, you are stuck.
  Most teams eventually add versioning anyway.
```

### 7.2 Stripe's 14-Year Backward Compatibility Strategy

Stripe is one of the most studied API designs in the industry, partly because they have maintained backward compatibility for over 14 years while continuously adding features.

The key insight: Stripe versions their API by date, not by endpoint. When Stripe ships a change that would be breaking, they create a new API version (date). Existing customers' API keys are pinned to the version they were using when they integrated. New customers get the latest version by default.

```
STRIPE VERSIONING MODEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Timeline:
  2013-08-01 — Original API launch
  2014-01-31 — Changed how subscription invoices work
  2014-06-17 — Changed how trials work
  ...
  2024-09-30 — Changed how payment intents return status
  2026-01-15 — (hypothetical) Changed error format

Customer A integrated in 2014:
  API-Version: 2013-08-01   (pinned to original)
  Gets 2013 behavior for subscriptions and all older endpoints.
  Subscription invoice change from 2014 does NOT affect them.
  They never need to update unless they want new features.

Customer B integrated in 2024:
  API-Version: 2024-09-30  (pinned to 2024 version)
  Gets new payment intent behavior.
  Gets all subscription changes up to 2024.

How it works internally:
  Every breaking change is wrapped in a version check:
  
  if api_version >= '2014-01-31':
      # new subscription invoice behavior
  else:
      # old subscription invoice behavior
  
  After 10 years, the code has hundreds of these checks.
  This is the maintenance cost of extreme backward compatibility.
```

Stripe's strategy works because payments infrastructure is mission-critical and breaking changes cause real financial harm to their customers. The cost they pay is internal complexity. Most teams do not need this level of backward compatibility — a 12-month deprecation window with migration support is sufficient for most internal and external APIs.

### 7.3 The Deprecation Lifecycle

```
DEPRECATION LIFECYCLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 1: ANNOUNCE (Month 0)
  - Publish migration guide
  - Email/notify all active users of the deprecated endpoint
  - Add Deprecation header to responses:
    Deprecation: true
    Sunset: Sat, 01 Jan 2028 00:00:00 GMT
    Link: <https://docs.example.com/migration>; rel="deprecation"
  - Add to API changelog
  - Create tracking (which customers are still using old version)

Phase 2: WARN (Months 1-6)
  - Send periodic reminders to customers who have not migrated
  - Track usage: is migration happening?
  - Provide migration tooling if possible (code mods, automated upgrade)
  - Offer office hours / support for migration questions

Phase 3: SUNSET (Month 6-12)
  - Reduce rate limits for deprecated endpoint
  - More aggressive warnings
  - Block new integrations against deprecated endpoint
  - Final notices

Phase 4: REMOVE (Month 12+)
  - Return 410 Gone for removed endpoint:
    HTTP/1.1 410 Gone
    Content-Type: application/json
    { "error": { "code": "endpoint_removed",
      "message": "This endpoint was removed on 2027-01-01. Please migrate to /v2/orders. See https://docs.example.com/migration" }}
  - Monitor for 410 hits — some clients always miss the notice

Timeline for external APIs: minimum 6 months, recommend 12 months.
Timeline for internal APIs: minimum 4 weeks (enough for migration).
Timeline for mobile SDKs: minimum 12 months (users don't update apps).
```

---

### Part 7 Brainstorming Questions

**Q: I'm building a new API and the team says "we'll version it when we need to." What's wrong with this?**

Everything. Versioning is a retroactive strategy that requires changes to every client to implement, and retroactive changes to clients are the thing versioning is supposed to avoid. If you build `/orders` without versioning and later realize you need to make a breaking change, you have two choices: (a) break every existing client, or (b) add versioning at that point — which requires all existing clients to update their URLs anyway.

The right answer: version from day one. `/v1/orders` costs you nothing extra. The `v1` prefix is a four-character commitment that buys you the ability to ship `v2` years later without breaking anyone. Teams that defer versioning always regret it, and the regret comes at the worst time — when you are under pressure to ship a new feature that requires a breaking change.

**Q: What is the difference between a "breaking change" and a "compatibility fix"?**

A breaking change is anything that causes existing clients to fail without their code changing. A compatibility fix is when you change your behavior to match what clients incorrectly expected you to do — which can itself be a breaking change for clients who correctly relied on the old behavior.

A real example: suppose your API returned `"status": "PENDING"` (uppercase) and the documentation said lowercase. Clients who followed the documentation wrote `if status == "pending"`. Clients who read the actual responses wrote `if status == "PENDING"`. If you "fix" the bug and return lowercase, you break all the clients who read the actual responses. Both groups have valid grievances. The only safe fix is: return both (`"status": "pending", "status_legacy": "PENDING"`) and deprecate the legacy field. Backward compatibility means you are responsible for the behavior you shipped, even if it was wrong.

**Q: How does Twitter's API v1 to v2 migration stand as a cautionary tale?**

Twitter deprecated v1 of their API in 2013 and started the transition to v1.1, then eventually began v2. The v1→v1.1 transition was painful because it changed authentication (from unsigned to OAuth), breaking every third-party Twitter client that used unsigned access. The migration notice was short, the window was months not years, and millions of users of third-party apps lost functionality overnight.

The lesson is not that Twitter broke their API — sometimes breaking changes are unavoidable. The lesson is about the migration experience: the timeline was too short, the migration guide was unclear, and Twitter did not provide adequate tooling for the transition. Third-party developers were rebuilding their authentication in a rush with ambiguous documentation. Good API deprecation is slow, heavily supported, and over-communicates. Twitter's API history is studied as a case study in what happens when a platform treats its developer ecosystem as an afterthought rather than a core product.

---

## Part 8: Error Design — Making Failures Recoverable

### 8.1 Errors as a First-Class Feature

Error design is treated as an afterthought by most engineers. The happy path gets careful design, documentation, and testing. Errors get `{ "error": "something went wrong" }` at 2 AM before the launch.

This is backwards. Callers spend more time handling errors than handling successes. A payment API integration has one success path and eight error paths: declined card, insufficient funds, invalid card number, expired card, wrong CVV, address mismatch, fraud block, network timeout. If the errors are opaque, every caller writes different bad recovery logic. If the errors are precise, callers can implement correct recovery logic once.

### 8.2 Anatomy of a Good Error Response

```json
BAD ERROR RESPONSE — what not to do:
HTTP/1.1 400 Bad Request
{
  "error": "Invalid request"
}
Problems:
- What was invalid? The caller has no idea what to fix.
- No machine-readable code — caller cannot branch on it.
- No request ID — how do you debug this in support?
- No documentation link — where does the caller look for help?


GOOD ERROR RESPONSE — the Stripe model:
HTTP/1.1 422 Unprocessable Entity
{
  "error": {
    "type": "validation_error",
    "code": "amount_too_small",
    "message": "The provided amount (10 cents) is below the minimum charge amount (50 cents for USD).",
    "param": "amount",
    "doc_url": "https://docs.example.com/errors/amount_too_small",
    "request_id": "req_abc123xyz"
  }
}
Good because:
- machine-readable "type" and "code" for programmatic branching
- human-readable "message" for developers and support
- "param" identifies which field was wrong
- "doc_url" links to the error's documentation page
- "request_id" lets you find this exact request in your logs


GOOD ERROR RESPONSE — field-level validation:
HTTP/1.1 422 Unprocessable Entity
{
  "error": {
    "type": "validation_error",
    "code": "invalid_request",
    "message": "Your request had 2 validation errors.",
    "request_id": "req_abc123xyz",
    "doc_url": "https://docs.example.com/errors/validation",
    "details": [
      {
        "field": "amount",
        "code": "required",
        "message": "Amount is required."
      },
      {
        "field": "currency",
        "code": "invalid_enum_value",
        "message": "Currency must be one of: USD, EUR, GBP. Got: 'DOLLARS'.",
        "allowed_values": ["USD", "EUR", "GBP"]
      }
    ]
  }
}
```

### 8.3 Error Taxonomy

Design your errors as a taxonomy, not a grab bag. The taxonomy has two dimensions: the HTTP status code (for routing) and the machine-readable error code (for branching within a status).

```
ERROR TAXONOMY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HTTP 400 — malformed request (body is not valid JSON, required header missing)
  error.type: "invalid_request_error"
  Recoverable: YES — fix the request format

HTTP 401 — authentication failed or missing
  error.type: "authentication_error"
  error.code: "api_key_invalid" | "api_key_expired" | "no_credentials"
  Recoverable: YES — provide valid credentials

HTTP 403 — authenticated but not authorized
  error.type: "authorization_error"
  error.code: "insufficient_permissions" | "account_suspended"
  Recoverable: MAYBE — contact support or request permission

HTTP 404 — resource not found
  error.type: "resource_not_found"
  error.code: "order_not_found" | "user_not_found"
  Recoverable: NO — do not retry

HTTP 409 — conflict with current state
  error.type: "conflict_error"
  error.code: "duplicate_idempotency_key" | "email_already_exists" | "optimistic_lock_failure"
  Recoverable: YES — resolve conflict, then retry with new idempotency key

HTTP 422 — valid request, invalid data
  error.type: "validation_error"
  error.code: <specific per-field error>
  Recoverable: YES — fix the specific fields

HTTP 429 — rate limited
  error.type: "rate_limit_error"
  error.code: "rate_limit_exceeded"
  Headers: Retry-After: 30
  Recoverable: YES — wait and retry

HTTP 500 — server error (bug)
  error.type: "server_error"
  error.code: "internal_error"
  Recoverable: MAYBE — retry with exponential backoff
  NOTE: Never expose internal details (stack traces, SQL errors)

HTTP 503 — service temporarily unavailable
  error.type: "service_unavailable"
  Headers: Retry-After: 60
  Recoverable: YES — retry after delay
```

### 8.4 Machine-Readable vs Human-Readable

Your error has two audiences: the developer debugging the integration, and the code that the developer writes to handle the error.

- **Machine-readable:** `"code": "insufficient_funds"` — this is what the code branches on. Must be stable (never change the value), specific (not `"payment_failed"`), and documented.
- **Human-readable:** `"message": "The card was declined because of insufficient funds. Please use a different card."` — this is what the developer sees in logs and what might be surfaced to end users. Can be improved over time, localized, made friendlier.

Always provide both. Code that receives an error and displays `error.message` directly is fine for debugging. Code that branches on `error.code` to show different UI is writing correct production code. You want to make both easy.

### 8.5 Errors That Help Callers Recover

The test of a good error: can the caller use only the information in the error response to understand what went wrong and fix it?

```
ERROR RECOVERY GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For 429 (rate limit): include Retry-After header
  The caller should wait exactly that many seconds before retrying.
  Without Retry-After, callers guess and often back off too aggressively
  or not aggressively enough.

For 422 (validation): include which field failed and why
  Without field-level detail, callers must guess which of their
  20 request fields was wrong.

For 409 (conflict): include what conflicted
  "An order with idempotency_key X already exists. Its ID is ord_123."
  The caller can then use the existing order rather than retrying.

For 401 (expired token): include how to refresh
  "Your access token has expired. Use your refresh token at /v1/tokens
   to obtain a new one." Better than just "unauthorized."

For 404: tell the caller if it existed and was deleted
  Use 410 Gone for permanently deleted resources.
  "This order was deleted on 2026-01-15." vs "order not found" — completely
  different recovery paths.

For 503: include scope of outage
  "Payment processing is temporarily unavailable. Other API operations
   are unaffected. Check status.example.com for updates."
  Callers should not assume the whole system is down.
```

---

### Part 8 Brainstorming Questions

**Q: Should error messages ever be shown directly to end users?**

Almost never from API errors directly. The `message` field in your error response is for developers — it can contain technical details, field names, internal terminology that would confuse end users. Client applications should translate API error codes into user-appropriate messages.

For example: API returns `{ "code": "insufficient_funds" }`. The mobile app should show "Your card was declined. Please check your account balance or try another card." — not the raw API error message. The API error might say "Stripe error: Your card has insufficient funds (Stripe code: card_declined, decline_code: insufficient_funds)" which is useful for a developer but bewildering for a user.

Design your error codes to be stable machine-readable values that clients can map to localized, user-appropriate messages in their own UI. Do not include end-user-facing text in API errors because different clients (mobile, web, SMS) need different presentations.

**Q: How do I debug a 500 error without exposing internal details in the response?**

The `request_id` field in your error response is the bridge. Every request should have a unique ID (generated at ingress, propagated through the whole request lifecycle in a tracing header). The error response includes this ID. The developer pastes it into your support portal or logs, and you can find every log line, every internal service call, every database query for that specific request.

This is why every error response must include a `request_id`. Without it, debugging a 500 is "we got a 500 sometime around 2pm" — nearly impossible to trace. With a request ID, it is "look up req_abc123xyz in Datadog" — trivial. Never return internal details (stack traces, SQL error messages, internal class names) in error responses — those are security leaks. Instead, log them internally with the request ID, and let the developer provide the request ID to get support.

---

## Part 9: API Security — The Defense-in-Depth Model

### 9.1 Authentication: API Keys vs OAuth2 vs JWT

Authentication answers: "Who are you?" These three schemes are the most common, and choosing the wrong one is a security anti-pattern.

```
AUTHENTICATION SCHEME COMPARISON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API KEYS
━━━━━━━━━━
How it works: Client presents a secret token in the Authorization header.
  Authorization: Bearer sk_live_abc123xyz

Best for:
- Server-to-server calls (no user involved)
- Third-party developer access
- Simple machine-to-machine auth

Security properties:
- Long-lived (do not expire automatically)
- Revocable at any time by the server
- No user session concept
- If leaked, valid until rotated

Implementation: hash the key before storing in DB (bcrypt or sha256).
Never store plaintext API keys. Never return the key after creation.
Show it once (at creation), then only show the prefix (sk_live_abc...).

OAuth2
━━━━━━━
How it works: User grants permission to a third party. Server issues
access tokens (short-lived) and refresh tokens (long-lived).
  Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...

Best for:
- "Login with Google/GitHub" flows
- Third-party apps that act on behalf of a user
- Delegated access with limited scope

Security properties:
- Access tokens are short-lived (15 min to 1 hour)
- Refresh tokens can be rotated on use
- Scoped: the token grants only specific permissions
- User can revoke third-party access without changing password

Flows:
- Authorization Code + PKCE: for browser/mobile apps
- Client Credentials: for server-to-server (machine-to-machine)
- Device Code: for TV/CLI apps without browser

JWT (JSON Web Tokens)
━━━━━━━━━━━━━━━━━━━━━
How it works: Token contains encoded claims. Server verifies signature.
  Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
  Decoded: { "sub": "usr_123", "exp": 1735689600, "scope": "read:orders" }

Best for:
- Stateless auth (no database lookup per request)
- Microservices where each service needs to verify identity
- Auth claims that are useful across services

Security properties:
- Stateless: server does not need to look up token in DB
- Cannot be revoked before expiry (major drawback)
- Short expiry (15-60 min) + refresh token pattern mitigates this
- Must use RS256 or ES256 signing (not HS256 for distributed systems)

WHEN TO USE WHICH:
- Public API, server-to-server: API keys
- User delegation, "login with X": OAuth2 Authorization Code
- Internal microservices, stateless: JWT
- Mobile/browser: OAuth2 with PKCE + JWT access tokens
```

### 9.2 Authorization: What to Check and Where

Authentication tells you who. Authorization tells you what they can do.

```
AUTHORIZATION LAYERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Layer 1: API Gateway (coarse-grained)
  - Is this API key valid?
  - Has this key been blocked/revoked?
  - Does this key have the right scope for this endpoint?
    (e.g., a read-only key cannot POST)

Layer 2: Service Layer (medium-grained)
  - Is this user allowed to use this feature?
    (e.g., is the user's plan tier high enough?)
  - Has the user's account been suspended?

Layer 3: Resource Layer (fine-grained)
  - Does this user own this specific resource?
    (e.g., can user A read order B? Only if B belongs to A)
  - This is the most commonly missed layer.

COMMON AUTHORIZATION BUG: Horizontal Privilege Escalation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BAD:
  GET /orders/ord_456
  Handler: fetch order by ID. Return it if found.
  Bug: ANY authenticated user can read ANY order if they know the ID.
  
GOOD:
  GET /orders/ord_456
  Handler:
    1. Fetch order by ID.
    2. Check: order.user_id == current_user.id
    3. If not, return 404 (not 403 — do not confirm existence)
    4. Return order.

NEVER rely on obscurity (unguessable IDs) for security.
Always check resource ownership explicitly.
IDs leak through logs, browser history, shared URLs.
```

### 9.3 Rate Limiting at the API Level

Rate limiting prevents abuse, protects service stability, and is a contract commitment: "You get N requests per M seconds."

```
RATE LIMITING STRATEGIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PER API KEY: most common for external APIs
  100 requests/second per API key.
  Implementation: Redis counter with TTL.
    INCR key:<api_key>:<current_minute>
    EXPIRE key:<api_key>:<current_minute> 60
    If count > limit: 429

PER USER: relevant when many keys per user
  1000 requests/hour per user account (across all their API keys).

PER ENDPOINT: expensive operations have lower limits
  GET /orders: 100/second
  POST /orders: 10/second
  POST /bulk-import: 1/minute

PER IP: defense against key-less abuse
  Useful at the API gateway before authentication.

RESPONSE HEADERS for rate limiting:
  X-RateLimit-Limit: 100          (max per window)
  X-RateLimit-Remaining: 43       (remaining in current window)
  X-RateLimit-Reset: 1735600000   (Unix timestamp when window resets)
  Retry-After: 30                 (seconds until retry safe) — only on 429

RATE LIMIT ALGORITHMS:
  Token Bucket: smooth rate limiting with burst allowance
    - Best for APIs with natural burst (batch operations)
    - Bucket refills at rate R, max capacity C
  
  Fixed Window: simple, but vulnerable to boundary bursts
    - 100 requests per minute means 200 in 2 seconds spanning a minute boundary
  
  Sliding Window: more accurate, more complex
    - No boundary burst problem
    - More memory-intensive in Redis
  
  Leaky Bucket: smooth output rate, queues excess
    - Good for rate-smoothing, not bursty patterns
```

### 9.4 Input Validation: Never Trust Callers

Input validation is your last line of defense before data hits your database and business logic.

```
INPUT VALIDATION CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

String fields:
  [ ] Maximum length enforced (prevents DB overflow and DoS)
  [ ] Minimum length enforced where applicable
  [ ] Allowed character set validated (especially for IDs, codes)
  [ ] No null bytes (\x00) — crash some string libraries
  [ ] HTML/script tags stripped or rejected for plain-text fields

Numeric fields:
  [ ] Minimum value (amount >= 0)
  [ ] Maximum value (amount <= reasonable max)
  [ ] Integer vs decimal: is a fractional amount valid?
  [ ] Overflow: int32 max = 2,147,483,647 (does that fit a price?)

Date/time fields:
  [ ] Valid format (ISO 8601)
  [ ] Reasonable range (not year 9999, not before 1900)
  [ ] Timezone handling explicit

ID fields:
  [ ] Format validation (UUID, prefixed ID format)
  [ ] Does the referenced resource exist?
  [ ] Does the caller own the referenced resource?

Lists/arrays:
  [ ] Maximum number of items
  [ ] Validate each item individually
  [ ] No duplicate items where uniqueness required

File uploads:
  [ ] File size limit
  [ ] File type validation (content-type AND magic bytes — do both)
  [ ] Virus scanning for untrusted files
  [ ] Store files outside the web root
```

### 9.5 What NOT to Log

Logging is critical for observability, but logging the wrong things creates security and compliance violations.

```
DO LOG:
  - Request ID (for tracing)
  - Timestamp, method, path, status code
  - Response time
  - User ID (for audit trail — not PII, just an identifier)
  - Error codes and types
  - Rate limit events
  - Authentication events (success/failure, IP)

DO NOT LOG:
  - Full request bodies (may contain PII or secrets)
  - Authorization header values (API keys, tokens)
  - Passwords (obvious, but some frameworks log all parameters)
  - Credit card numbers, CVVs, bank account numbers
  - SSNs, passport numbers, government IDs
  - Health information (HIPAA)
  - Private messages / chat content
  - Idempotency keys (could be used to replay operations)

WHAT TO DO INSTEAD:
  - Log a hash of sensitive values if you need to correlate:
    log("API key hash: " + sha256(api_key)[:8])
    This lets you trace "which key made this request" without
    logging the key itself.
  - Log that a body was received and its Content-Length, not its content.
  - Scrub logs of PII patterns before they reach long-term storage.
```

---

### Part 9 Brainstorming Questions

**Q: When should I use API keys vs JWTs for an internal microservices setup?**

For internal service-to-service calls, JWTs are usually better than API keys. The reason: JWTs are stateless — each service can verify a JWT by checking the signature against the public key without making a network call to an auth service. API key validation typically requires a database or cache lookup ("is this key still valid?"), which adds latency and a dependency on the auth service being available.

The pattern: services authenticate with a short-lived JWT (15-minute expiry). When the token expires, the service fetches a new one from the auth service (using the Client Credentials OAuth2 flow). Each service validates the JWT signature locally. The auth service is only involved in token issuance, not in every request — this is significantly more scalable.

The trade-off: you cannot revoke a JWT before it expires (unless you maintain a revocation list, which reintroduces the stateful lookup). For internal services where you control all the code, this is acceptable — if a service is compromised, you shut it down rather than revoking credentials. For external APIs where a key might be leaked, API keys (which can be immediately revoked) are safer.

**Q: What is the right rate limit for a public API and how do I decide?**

The starting point is your capacity: if your service can handle 10,000 requests per second and you have 100 customers, a limit of 100 requests per second per customer gives you headroom. But that calculation ignores actual usage patterns and the cost of different operations.

The right approach: measure before you set limits. Look at your actual traffic distribution. What does the 99th percentile customer use per second? Set your limit at something like 10x that, so normal usage never hits the limit. Set tiered limits: free tier (lower), paid tier (higher), enterprise tier (highest or custom). Expensive operations (writes, bulk operations) get lower limits than cheap operations (reads).

Document your rate limits clearly before customers integrate. Surprise rate limits are one of the most common complaints about third-party APIs — developers build integrations that work fine in testing (low volume) but fail at production scale when they hit a rate limit they did not know existed.

---

## Part 10: Designing for Developer Experience

### 10.1 Documentation as a Feature

The best API in the world is worthless if developers cannot figure out how to use it. Documentation is not a supplement to the API — it is part of the product. Stripe's success is partly attributable to having the best API documentation in the payments industry: interactive examples, code samples in every major language, clear error explanations, a complete API reference, and conceptual guides.

```
DOCUMENTATION ANATOMY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Level 1: Quickstart
  - Get a developer making a real API call in under 5 minutes
  - One page, copy-pasteable code, immediate feedback
  - Shows the "hello world" of your API
  - "Make your first charge in 3 minutes"

Level 2: Conceptual Guides
  - Explain the mental model: what is a Charge vs a PaymentIntent?
  - When to use which approach
  - Common patterns and best practices
  - These guide developers through design decisions, not just syntax

Level 3: API Reference
  - Every endpoint, every parameter, every response field
  - Type, required vs optional, valid values, defaults
  - Example request + example response for every endpoint
  - Error codes specific to each endpoint
  - This is the encyclopedia; developers use it to look up specifics

Level 4: Changelog
  - Every API change, with date and migration guidance
  - Breaking changes highlighted prominently
  - Old behavior → new behavior explained
  - This is what customers read when something breaks

Level 5: Error Reference
  - Every error code with: meaning, cause, how to fix it
  - Linked from error responses (the doc_url field)
  - "You got error X. Here's what it means and how to resolve it."
```

### 10.2 SDKs and Client Libraries

A great API has SDKs in the languages your customers use. SDKs reduce integration time from days to hours.

```
SDK DESIGN PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Language-idiomatic design:
  Python: use snake_case, context managers, type hints
  JavaScript: use camelCase, Promises/async-await, TypeScript
  Java: use builder pattern, checked exceptions, fluent APIs
  Go: use error returns, small interfaces, functional options

SDK must NOT just be a thin wrapper:
  - Handle authentication (token refresh, key rotation)
  - Handle retries with exponential backoff (on 429 and 503)
  - Handle pagination (auto-paginating list iterators)
  - Handle error deserialization (map error codes to typed exceptions)
  - Handle idempotency key generation
  - These are the things every developer gets wrong independently

Example of good SDK design:
  # Stripe Python SDK — developer does not manage pagination
  for order in stripe.Order.list(limit=100, auto_paginate=True):
      process(order)  # SDK automatically fetches next pages
  
  # Stripe Python SDK — retries are automatic
  try:
      charge = stripe.Charge.create(
          amount=5000,
          currency="usd",
          source="tok_visa"
      )
  except stripe.error.CardError as e:
      # Specific error — card was declined
      handle_decline(e.error.code)
  except stripe.error.RateLimitError:
      # SDK already retried with backoff — this is a final failure
      alert_ops()

Keep SDKs in sync with the API:
  - Use code generation from your OpenAPI or proto spec
  - Manual SDKs drift and become wrong — automate generation
  - Publish new SDK versions on every API version that affects clients
```

### 10.3 API Sandbox and Test Mode

Every developer should be able to test integrations without real-world side effects. Stripe's test mode is the industry standard for how to do this.

```
SANDBOX DESIGN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Two modes, same API surface:
  Test mode: sk_test_abc123 — uses test infrastructure, no real charges
  Live mode: sk_live_abc123 — real operations, real money

Test mode features:
  - Test card numbers that trigger specific responses:
    4242 4242 4242 4242 → success
    4000 0000 0000 0002 → card declined
    4000 0000 0000 9995 → insufficient funds
  - Instant clock for testing subscription billing without waiting
  - Webhook test triggers (simulate an event without real cause)
  - Full API parity (every live feature works in test)

Sandbox vs production parity is critical:
  The sandbox must behave identically to production for all
  operations except real side effects. If the sandbox is missing
  features or has different error behavior, developers test against
  a fiction and get surprised in production.

What makes a bad sandbox:
  - Missing endpoints ("not available in test mode")
  - Different rate limits (too lenient in test, strict in production)
  - Different error codes
  - Different response shapes
  - Stale data or missing reference data
```

### 10.4 Webhook Design

Webhooks let your service push events to customers rather than requiring them to poll. They are the publish side of a publish-subscribe pattern over HTTP.

```
WEBHOOK DESIGN PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Event envelope: all webhooks have the same shape
  {
    "id": "evt_abc123",
    "type": "order.completed",
    "created": 1735600000,
    "api_version": "2026-06-01",
    "data": {
      "object": { ...the order... }
    }
  }
  
  Same structure regardless of event type.
  "type" tells the receiver how to handle it.
  "data.object" contains the actual event data.

Signature verification: every webhook must be signed
  X-Signature: sha256=hmac(body, webhook_secret)
  The receiver computes the expected signature and compares.
  This prevents attackers from spoofing webhook events.

Delivery guarantees: at-least-once
  Webhooks are delivered at-least-once — the receiver may get
  duplicates. The receiver must be idempotent:
    1. Check: have I already processed event evt_abc123?
    2. If yes, return 200 OK immediately
    3. If no, process and mark as processed

Retry policy: back off and retry on failure
  If the receiver returns anything other than 2xx, retry.
  Suggested schedule: 1m, 5m, 30m, 2h, 6h, 24h.
  After final failure: mark as failed, alert customer, archive event.

The "thin envelope" pattern: webhooks for notification, API for data
  Do NOT include all the data in the webhook — include just enough
  to identify what happened. The receiver calls the API to get the
  full data. This prevents webhook payloads from becoming huge and
  from going stale (if the order was updated between event and delivery).
  
  BAD: Webhook contains entire order (500 fields, stale by delivery)
  GOOD: Webhook contains order ID and event type → receiver calls
        GET /orders/{id} to get current state

Webhook event catalog:
  Document every event type. For each:
  - What triggers it
  - What data it contains
  - Which order events fire (e.g., order.created fires before order.payment.captured)
  - Idempotency considerations
```

---

### Part 10 Brainstorming Questions

**Q: Who should own the API documentation — the API team or a separate technical writing team?**

The answer that scales best: engineers own the reference documentation (because they know what every parameter does and what every error means), and technical writers own the conceptual and tutorial documentation (because they know how to explain things to developers who have not read the source code). Neither group alone produces great documentation.

The failure mode when engineers own everything: accurate but incomprehensible. Engineers write for people who already understand the system. They skip the "why" because it is obvious to them. They use internal terminology without defining it. The failure mode when technical writers own everything: polished but wrong. Writers do not understand edge cases, error conditions, or the subtle behavior differences between fields. The best documentation teams pair an engineer with a technical writer for every major feature.

One practical discipline: require engineers to document the API before writing the implementation. If you cannot explain what an endpoint does, its parameters, and its error conditions in plain language before coding it, you have not thought through the design well enough. Documentation-first API design produces better APIs.

**Q: How do you handle webhook security when the customer's endpoint is slow or unreliable?**

This is an operational problem as much as a design problem. First, delivery retries with exponential backoff handle transient failures. For persistent failures, use a dead-letter queue — events that exceed the retry budget are stored and the customer is alerted. Give customers a way to replay events from the dead-letter queue once they fix their endpoint.

For slow endpoints: set an aggressive timeout (5-10 seconds). Receivers should acknowledge the webhook immediately (return 200) and process asynchronously. Document this explicitly: "Return 200 before processing. Long-running webhook handlers should enqueue the event and process it in the background." The common mistake is building a webhook receiver that does database work synchronously before returning 200 — this times out and triggers retries, causing duplicates.

For rate limiting outbound webhooks: if a customer endpoint is consistently slow, throttle delivery to avoid overwhelming it. Some systems implement adaptive rate limiting that reduces delivery speed when a receiver is struggling, gradually ramping back up when it recovers.

---

## Part 11: API Design in L6 Interviews

### 11.1 What Interviewers Are Actually Testing

In an L6 system design interview with an API design component, the interviewer is not checking whether you know REST semantics. They know you know REST. They are checking:

1. **Do you design the full contract, not just the happy path?** — Can you enumerate the error conditions, design field-level validation errors, specify idempotency behavior, and define the rate limiting strategy?

2. **Do you reason about backward compatibility from the start?** — When you design `/v1/orders`, do you immediately think about what it would take to ship `/v2/orders` and how you would migrate clients?

3. **Do you understand scale implications of API choices?** — Do you know why cursor pagination beats offset at scale? Do you know the N+1 problem in GraphQL?

4. **Do you think about the developer experience?** — Do you design errors that help callers recover? Do you include `request_id` for debuggability? Do you think about the SDK?

5. **Do you apply the right tool for the right context?** — REST for external APIs, gRPC for internal service-to-service with streaming, GraphQL when client-driven data fetching is genuinely needed.

### 11.2 L5 vs L6 Calibration for API Design Questions

```
L5 API DESIGN RESPONSE:
  "I'd use REST with JSON. The endpoints would be:
   POST /orders to create an order,
   GET /orders/{id} to get an order,
   GET /orders to list orders with pagination.
   I'd use 201 for creation, 200 for reads, 404 for not found,
   400 for bad requests."
  
  Good: correct REST semantics, appropriate status codes.
  Missing: error taxonomy, idempotency, backward compatibility,
  versioning strategy, developer experience, scale implications.

L6 API DESIGN RESPONSE:
  "I'd use REST with JSON for the external API, versioned as /v1/.
   
   For creation: POST /v1/orders requires an Idempotency-Key header —
   this endpoint creates financial records and must not duplicate on retry.
   The response is 201 Created with Location header pointing to the
   new resource.
   
   For errors: validation failures are 422 with field-level detail,
   conflicts are 409, rate limits are 429 with Retry-After header.
   Every error includes a machine-readable code, a human-readable
   message, a request_id for tracing, and a doc_url.
   
   For pagination: I'd use cursor-based pagination — offset breaks
   at scale because of phantom reads and expensive COUNT queries.
   The cursor encodes the sort key of the last item.
   
   For versioning: URL versioning with /v1/. When v2 is needed,
   I'd deprecate v1 with a 12-month window, add Deprecation and
   Sunset response headers, and document the migration guide.
   
   For internal services calling the orders service, I'd use gRPC
   with protobuf — type safety, streaming support for real-time
   order status updates, and 3-10x better performance than JSON.
   
   For developer experience: test mode (sk_test_ keys) with test
   card numbers that trigger specific errors, an SDK that handles
   retries, pagination, and error deserialization automatically,
   and an API changelog."
  
  This is a contract. This is an engineering discipline. This is L6.
```

### 11.3 Common Interview Mistakes

**Mistake 1: Using 200 OK for everything**
Returning `{ "success": false, "error": "..." }` in a 200 response body. Every interviewer knows this is wrong. Use the correct HTTP status code.

**Mistake 2: Designing only the happy path**
Saying "POST /orders to create an order" without specifying: what if the user doesn't exist? What if an item is out of stock? What if the request is a duplicate? What if the caller hits the rate limit? The error cases are what separate good designs from great designs.

**Mistake 3: Saying "I'd use GraphQL" without knowing the N+1 problem**
If you propose GraphQL, you must be able to explain DataLoader, query depth limits, query cost estimation, and why HTTP caching doesn't apply. If you cannot, propose REST — it is not a lesser choice.

**Mistake 4: Forgetting backward compatibility**
Designing an API and not mentioning versioning, or saying "we'll add versioning later." Versioning strategy is part of the API design, not a future concern.

**Mistake 5: Using offset pagination for a high-scale collection**
If the system you are designing has billions of records (social feed, event stream, orders for a large merchant), offset pagination is wrong. The interviewer is testing whether you know why and whether you know the alternative.

**Mistake 6: Missing idempotency for write operations**
Any POST that creates a financial record, sends a message, or triggers an irreversible action needs an idempotency strategy. Forgetting this in a payments or messaging API design is a significant miss.

---

### Part 11 Brainstorming Questions

**Q: In an interview, the question is "design the API for a ride-sharing app." How do I structure my answer?**

Start by establishing scope: "Is this the driver-facing API, the rider-facing API, or both? Is this a mobile app API or internal service APIs?" Then work through resource modeling before jumping to endpoints.

Key resources: Rider, Driver, Ride (the trip itself), Location, Payment. Then think through the lifecycle of a ride: request → match → pickup → in-progress → complete → payment. Each state transition is an API call. The tricky parts: real-time location updates (streaming via WebSocket or gRPC server streaming, not REST polling), the matching algorithm (internal service, gRPC), and payment (idempotency keys required).

For an L6 answer: design the main resource endpoints, explain your pagination strategy for ride history (cursor-based), specify how you handle location updates (streaming, not polling), call out that the payment endpoint needs an idempotency key, mention that driver-facing and rider-facing APIs might warrant different API surfaces, and note that this is a good use case for gRPC internally (driver location streaming) alongside a REST external API.

**Q: An interviewer asks, "What makes the Stripe API so good?" How do I answer that without just saying "good documentation"?**

Documentation is part of it, but the deeper answer is that Stripe designed for reliability in a domain where errors are catastrophic. Their idempotency key pattern means retries never double-charge. Their date-based versioning means customers never have breaking changes forced on them. Their error codes are specific enough that every failure case has a programmatic response. Their test mode is a perfect replica of production behavior. Their webhook signatures prevent spoofing.

The philosophical answer: Stripe designed the API as if their customers' businesses depended on it — because they do. Every design decision prioritizes correctness over convenience for the API developer. It is more work to build an idempotency key system, to maintain 14 years of API versions, to write 200 specific error codes. But that extra work is exactly what financial infrastructure requires. The lesson: know your domain's reliability requirements, and let them drive your API design decisions.

---

## Common Interview Mistakes — Summary

1. **Returning 200 for errors.** Using HTTP status codes correctly is table stakes at L6. Never return a 200 with `"success": false` in the body.

2. **Offset pagination for high-scale collections.** Know why cursor pagination beats offset at scale (no phantom reads, constant-time queries, no COUNT(*) needed), and be able to explain how cursor pagination is implemented.

3. **Forgetting idempotency on write operations.** Any POST that creates financial records, sends messages, or triggers irreversible external actions needs an idempotency strategy. Stripe-style idempotency keys are the standard.

4. **Saying "GraphQL" without knowing the N+1 problem.** GraphQL is not free. If you propose it, explain DataLoader for batching, query depth limits for security, and why HTTP caching does not work natively.

5. **No versioning strategy.** Designing an API without a versioning strategy is designing a system with no migration path. `/v1/` costs four characters and buys you unlimited future flexibility.

6. **Error design as afterthought.** Designing errors as `{ "error": "something failed" }` instead of a typed taxonomy with machine-readable codes, field-level detail, request IDs, and documentation links. The error cases are more important than the happy path.

---

## Exercises

**Exercise 1: Design the REST API for a food delivery system**
Design the complete REST API for a food delivery platform including: customers, restaurants, menus, orders, and delivery tracking. Specify: resource hierarchy, all endpoints (method + path), request/response shapes for create and get, status codes including error cases, pagination strategy for order history, idempotency strategy for order creation, and versioning approach.

**Exercise 2: Break-and-fix an existing API**
You are given this API for creating a user:
```
POST /createUser
{
  "name": "Alice",
  "email": "alice@example.com",
  "password": "hunter2"
}
Response 200:
{
  "success": true,
  "userId": 123,
  "created": "June 20 2026 10:00 AM"
}
```
Identify every design mistake (there are at least 8). Then design the corrected API.

**Exercise 3: Design cursor pagination**
Implement cursor pagination for a `/v1/transactions` endpoint. The transactions table has 50 million rows. Write the SQL query that uses a cursor, the server-side cursor encoding logic (what does the cursor contain and how is it encoded?), the response shape, and the error response when a cursor is invalid.

**Exercise 4: Design an idempotency system**
Design the full idempotency implementation for `POST /v1/payments`. Include: what gets stored (key → what?), TTL, behavior when the first request is still in-flight, behavior when the original request failed, and behavior when the same key is sent with a different request body.

**Exercise 5: Error taxonomy for a payments API**
Design the complete error taxonomy for a payments API. For each error category (authentication, authorization, validation, rate limit, server error, payment-specific errors like declined, insufficient funds, fraudulent), specify: HTTP status code, `error.type`, `error.code` values, and what information should be in `error.details`.

**Exercise 6: gRPC proto design**
Design the `.proto` file for a notification service that: creates notifications, lists notifications for a user (paginated), marks notifications as read, and streams new notifications in real time. Include all four message types, the service definition, appropriate field types, and a reserved field for backward compatibility.

**Exercise 7: Backward compatibility test**
Given this REST API response:
```json
{ "id": "ord_123", "status": "PENDING", "amount": 50.00, "user": 456 }
```
The team wants to make these changes: (a) rename `PENDING` to `pending` (lowercase), (b) add a new required field `shipping_address`, (c) change `user` from an integer ID to a user object, (d) change `amount` from float to `amount_cents` integer. For each change, classify it as breaking or non-breaking, explain why, and design the backward-compatible migration.

**Exercise 8: Webhook system design**
Design the webhook delivery system for an e-commerce platform. Include: event schema, signature verification mechanism, delivery retry policy, handling of slow receivers (timeout), idempotency for receivers, the dead-letter queue, and how customers register and manage webhook endpoints.

---

## Homework

**Homework 1: API audit**
Pick any public REST API you have used (GitHub, Stripe, Twilio, Shopify, or similar). Read their API documentation and identify: (a) what they do well that matches this chapter's principles, (b) two things that seem to violate the principles, (c) how they handle versioning and deprecation. Write a one-page analysis.

**Homework 2: Design an SDK**
Pick a REST API you designed or use. Design (not implement) an SDK for it in your preferred language. Focus on: what operations the SDK abstracts (retry logic, pagination, error deserialization), what the SDK's interface looks like for the three most common operations, and how the SDK handles token refresh. Write the interface (not the implementation) as code.

**Homework 3: Read the Stripe API docs**
Go to stripe.com/docs/api and read: the Authentication section, the Errors section, any one resource (e.g., PaymentIntents), and the Webhooks section. Identify three design decisions Stripe made that you would not have made without reading this chapter, and explain why each decision is correct.

**Homework 4: Implement idempotency with Redis**
Build a working implementation of the idempotency key pattern in any language using Redis. Your implementation should: store idempotency keys with 24-hour TTL, handle concurrent requests with the same key (one wins, one waits), store and replay both success and error responses, and return 409 for same-key-different-body. Test it by simulating a duplicate request.

**Homework 5: Proto backward compatibility drill**
Start with a simple `.proto` file (3-4 messages, one service). Make ten proposed changes to it. For each, determine if it is backward compatible or breaking, and explain why. Then fix the breaking changes to be backward compatible. This exercise builds the intuition for proto field numbers and backward compatibility rules that staff engineers need to review proto changes in code review.

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════╗
║                     CHAPTER 100: KEY TAKEAWAYS                      ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  APIs ARE CONTRACTS                                                  ║
║  Every design decision compounds. Breaking changes at scale cost     ║
║  weeks of coordination. Design the contract before the code.         ║
║                                                                      ║
║  REST FUNDAMENTALS                                                   ║
║  Nouns not verbs in URLs. HTTP verbs for actions. Status codes       ║
║  are part of the contract: 201 for create, 422 for validation,       ║
║  409 for conflict, 429 for rate limits. Never 200 for errors.        ║
║                                                                      ║
║  CURSOR PAGINATION BEATS OFFSET AT SCALE                             ║
║  Offset has phantom reads, expensive COUNT(*), and O(n) database     ║
║  scans. Cursor pagination is O(1) and stable under concurrent        ║
║  modifications. Use cursor for any high-scale collection.            ║
║                                                                      ║
║  IDEMPOTENCY IS REQUIRED FOR WRITE OPERATIONS                        ║
║  Networks fail. Clients retry. POST operations that create           ║
║  financial records, send messages, or trigger external actions       ║
║  MUST be idempotent. Stripe's idempotency key pattern is the         ║
║  standard: client-generated UUID, server stores response.            ║
║                                                                      ║
║  gRPC FOR INTERNAL, REST FOR EXTERNAL                                ║
║  gRPC: better performance (binary), streaming support, strict        ║
║  contracts. REST: universal browser support, HTTP caching,           ║
║  simpler toolchain. Use each where it fits.                          ║
║                                                                      ║
║  PROTOBUF BACKWARD COMPATIBILITY                                     ║
║  Never reuse field numbers. Never remove fields without reserving.   ║
║  Never change field types. You CAN add new fields, new RPCs.         ║
║  The field number, not the name, is the wire format.                 ║
║                                                                      ║
║  GRAPHQL HAS REAL COSTS                                              ║
║  N+1 problem requires DataLoader. HTTP caching does not work.        ║
║  Arbitrary queries create security surface. GraphQL is excellent     ║
║  for BFF pattern with multiple clients needing different shapes.     ║
║  Know the trade-offs before proposing it.                            ║
║                                                                      ║
║  VERSION FROM DAY ONE                                                ║
║  /v1/ costs four characters. Not versioning costs weeks of           ║
║  coordination when you need a breaking change. Use URL versioning    ║
║  for external APIs. Deprecation lifecycle: announce → warn →         ║
║  sunset → 410 Gone.                                                  ║
║                                                                      ║
║  DESIGN ERRORS FIRST                                                 ║
║  Good errors: machine-readable code, human-readable message,         ║
║  field-level detail, request_id, doc_url. Callers spend more         ║
║  time handling errors than successes. Errors that help callers       ║
║  recover are a product feature, not an afterthought.                 ║
║                                                                      ║
║  SECURITY IS DEFENSE IN DEPTH                                        ║
║  Authentication → authorization → resource ownership check.          ║
║  Never skip the ownership check. Rate limit per key, per user,       ║
║  per endpoint. Never log credentials, tokens, or PII.                ║
║                                                                      ║
║  DX IS PART OF THE API                                               ║
║  Documentation, sandbox, SDKs, and webhooks are not extras.          ║
║  They are the product. Stripe's success is 50% API design and        ║
║  50% developer experience. Build both.                               ║
║                                                                      ║
║  THE L6 SIGNAL                                                       ║
║  L5 designs the happy path. L6 designs the full contract:            ║
║  errors, idempotency, versioning, pagination, security,              ║
║  observability, and developer experience — before writing code.      ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

*Chapter 100 complete. Next: Chapter 101 — Security Mindset.*
