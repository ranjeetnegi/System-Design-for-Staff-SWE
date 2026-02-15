# API Gateway: Auth, Rate Limit, Route, Proxy

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Airport security checkpoint. One line. Multiple checks. ID verification—who are you? Auth. Baggage scan—is your luggage valid? Validation. Boarding pass check—which flight? Routing. "Too many people in line"—management. Rate limiting. All in one place. Before you board. API gateway does the same for API requests. Authenticate. Validate. Rate-limit. Route. Transform. Log. All before the request reaches your service.

---

## The Story

The API gateway isn't just a router. It's a pipeline. Request comes in. Step 1: **Auth**. Is there a valid token? JWT? API key? OAuth? No token? 401. Invalid? 403. Gateway blocks before hitting your service. Your service doesn't need auth logic—gateway did it.

Step 2: **Rate limiting**. Too many requests from this IP? This user? This API key? Throttle. 429 Too Many Requests. Protect your backend from abuse. DDoS mitigation. Fair usage. Gateway enforces. Service stays clean.

Step 3: **Validation**. Request body malformed? Schema wrong? Gateway rejects. 400 Bad Request. Don't waste service CPU on invalid input. Validate at the edge.

Step 4: **Routing**. Path /orders → order service. Path /users → user service. Maybe path rewriting. /v1/orders → /orders (internal). Version in URL, service doesn't care.

Step 5: **Proxy**. Forward to backend. Load balance. Retry. Timeout. Response back to client. Maybe aggregate multiple backend calls into one. BFF—Backend for Frontend—pattern. Gateway assembles the response.

All in one place. Centralized. Change auth? Update gateway config. Add rate limit? Gateway. Services focus on business logic.

---

## Another Way to See It

Think of a bouncer at a club. ID check (auth). Dress code (validation). "We're at capacity" (rate limit). "VIP section that way" (routing). Then you're in. The DJ (your service) just plays music. Doesn't check IDs. The bouncer handled it.

Or a passport control. Check passport (auth). Validate visa (validation). "Line is full, wait" (rate limit). Stamp and direct to gate (routing). The airplane (service) doesn't do border control. Gate did it.

---

## Connecting to Software

In implementation: Kong has plugins for auth (JWT, key-auth), rate limiting (per consumer, per IP), request validation. AWS API Gateway: authorizers (Lambda, Cognito), usage plans (rate limit), request validation (JSON schema). Same idea across providers. Configure the pipeline. Requests flow through.

Order matters. Auth before route—why route unauthorized traffic? Rate limit early—reject before expensive processing. Validation before proxy—don't forward garbage.

**Logging and observability:** Gateway sees every request. Log request ID, path, user, latency, status. Central place for access logs. Feed to analytics, security monitoring. "Who hit this endpoint? How often? From where?" Gateway is the observability choke point. Use it. Trace ID propagation: pass request ID to backends for distributed tracing. One place to add headers.

**Transformation:** Gateway can modify requests and responses. Add headers. Strip internal fields. Convert between formats (JSON to XML for legacy clients). Response compression (gzip). One layer for cross-cutting transformations. Keeps services focused on business logic. Gateway handles protocol details. API key to user mapping: gateway resolves API key to internal user ID. Backend receives user context. Gateway does the lookup. Services stay simple. The gateway pipeline is your cross-cutting concern layer. Centralize it. Don't scatter auth and rate limiting across every service.

---

## Let's Walk Through the Diagram

```
    API GATEWAY REQUEST PIPELINE

    Client Request
         │
         ▼
    ┌─────────────┐
    │  1. AUTH   │  ← Valid token? API key? 401/403 if not
    └─────┬──────┘
          │
          ▼
    ┌─────────────┐
    │ 2. RATE    │  ← Too many requests? 429 if over limit
    │   LIMIT    │
    └─────┬──────┘
          │
          ▼
    ┌─────────────┐
    │ 3. VALIDATE│  ← Schema OK? 400 if invalid
    └─────┬──────┘
          │
          ▼
    ┌─────────────┐
    │ 4. ROUTE   │  ← /orders → Order Service, /users → User Service
    └─────┬──────┘
          │
          ▼
    ┌─────────────┐
    │ 5. PROXY   │  ← Forward to backend. Response back to client
    └─────────────┘
```

---

## Real-World Examples (2-3)

**Example 1: Stripe.** API key required. Gateway validates. Invalid key? 401 before any logic. Rate limit per key. Free tier: 100 req/sec. Paid: more. Gateway enforces. Stripe's services never see unauthorized or over-limit requests.

**Example 2: Twilio.** Auth via Account SID + Auth Token. Rate limit by account. Gateway handles. Webhook validation (signature). All at the edge. Backend focuses on processing calls, messages.

**Example 3: Netflix.** Gateway (Zuul) does auth (validate subscription, device), rate limit (prevent abuse), route to hundreds of services. A/B testing via gateway—route 10% to new version. All cross-cutting concerns in one layer.

---

## Let's Think Together

**Should business logic live in the gateway?**

No. Auth, rate limit, routing, validation—infrastructure concerns. "Is this user allowed?" Yes. "Does this user have permission to delete *this* resource?" That's business logic. Service should check. Gateway does coarse-grained: authenticated or not. Service does fine-grained: can this user do this action on this resource?

**What if different services need different auth?**

Gateway can route by path, then apply different auth. /admin/* needs admin token. /public/* needs no auth. /api/* needs user token. Configure per-route. Or use a custom authorizer (Lambda) that implements complex logic. Gateway calls it. Still keeps auth at the edge.

---

## What Could Go Wrong? (Mini Disaster Story)

A company puts strict rate limits on the gateway. 100 req/sec per user. Legitimate bulk import feature needs 1000 req/sec. Users complain. They raise the limit. A bad actor scripts 999 req/sec. Service overloads. They add per-endpoint limits. /import gets higher limit. Complexity grows. Lesson: rate limits need thought. Different endpoints, different needs. One global limit is rarely right. Tune. Monitor. Iterate.

---

## Surprising Truth / Fun Fact

Kong, the popular open-source API gateway, started in 2015. It's built on Nginx + Lua. The plugin architecture—auth, rate limit, logging—all pluggable. Hundreds of plugins now. Same idea: centralize cross-cutting concerns. Let services focus on what they do. The gateway is the "platform" layer many companies build once and reuse.

---

## Quick Recap (5 bullets)

- **Auth**: Gateway validates token, API key, OAuth. 401/403 before request reaches service. Centralized.
- **Rate limit**: Throttle by IP, user, API key. 429 when over limit. Protects backend from abuse and overload.
- **Validation**: Schema check. Malformed request? 400 at gateway. Service doesn't waste cycles.
- **Routing**: Map path to backend. /orders → order service. Versioning. Path rewriting.
- **Proxy**: Forward to backend. Load balance. Retry. Timeout. Single place for all cross-cutting concerns.

---

## One-Liner to Remember

API gateway = airport security. Auth, rate limit, validation, routing—all in one checkpoint. Your service just processes the cleared request.

---

## Next Video

Next up: **Service Mesh**—a security guard next to every service. TLS, retries, observability. Transparent. The neighborhood where every house has its own guard.
