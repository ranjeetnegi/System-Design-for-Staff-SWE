# API Gateway Design: Pipeline and Components

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

An airport terminal. Before you board a flight, you pass through: ticket check → ID verification → security scan → gate assignment → boarding. Each step is a stage in a PIPELINE. You can't skip. You can't reverse. An API gateway works the same—each request passes through stages: authentication → rate limiting → request routing → request transformation → logging → forwarding to the right service. One pipeline. Every request. That's how you build APIs at scale.

---

## The Story

A client sends a request. "GET /users/123." Where does it go? You have 50 microservices. User service. Order service. Notification service. Analytics. The client doesn't know. Shouldn't know. The API gateway does.

It receives the request. Checks: Who are you? (Auth.) Are you allowed to make this many requests? (Rate limit.) Where does /users go? (Route.) Does the request need to be transformed? (Transform.) Then: forward to the User Service. Log everything. Return the response. The gateway is the single entry point. The bouncer. The traffic cop. Everything flows through it. No exceptions.

Without a gateway, every service does auth, rate limiting, logging. Duplicated. Inconsistent. A nightmare to change. "We need to update rate limits." Update 50 services? No. With a gateway, you do it once. Centralize the cross-cutting concerns. Services focus on business logic. The gateway handles the rest. This pattern powers every major API—Stripe, AWS, Google. One door. Many rooms behind it. You control who gets in and where they go.

---

## Another Way to See It

Think of a reception desk at a large office building. Visitor arrives. Reception checks: Do you have an appointment? (Auth.) Are you on the list? (Authorization.) Which floor? (Route.) Sign the guest book. (Log.) Then: directions to the right office. The reception doesn't do the meeting. It gets you there. Same for API gateway. It doesn't process business logic. It gets the request to the right service. And it enforces the rules before letting anyone through. No badge? No entry. Too many visits today? Come back tomorrow. Wrong floor? Redirect. The building trusts the reception. Your services trust the gateway.

---

## Connecting to Software

**Pipeline.** Auth → Rate Limit → Route → Transform → Forward → Log. Each stage can pass or reject. Auth fails? 401. Rate limit exceeded? 429. Route not found? 404. The pipeline is ordered. Auth before rate limit. Rate limit before routing. Why? No point routing a request from an unauthenticated user. No point rate limiting after you've already forwarded. Order matters. Think through the stages. Each one filters. By the end, only valid traffic reaches your services.

**Components.** Router: maps URL to service. /users → User Service. /orders → Order Service. Auth module: JWT validation, API keys, OAuth. Rate limiter: token bucket, sliding window. Request/response transformer: add headers, modify payload, translate between versions. Circuit breaker: if a service is down, fail fast. Don't cascade. Logging: every request, response time, status code. Metrics for dashboards. Observability starts at the gateway.

**Popular gateways.** Kong: open-source, plugin-based. AWS API Gateway: managed, serverless. Nginx: simple reverse proxy, extend with Lua. Envoy: modern, observability built-in. Each has trade-offs. Kong: flexibility. AWS: no ops. Nginx: performance. Envoy: cloud-native. Pick by your context. They all implement the same pipeline. The concept is universal. The implementation varies.

---

## Let's Walk Through the Diagram

```
API GATEWAY - REQUEST PIPELINE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   CLIENT REQUEST                                                 │
│        │                                                         │
│        ▼                                                         │
│   ┌─────────┐   ┌─────────────┐   ┌─────────┐   ┌────────────┐  │
│   │  AUTH   │──►│ RATE LIMIT  │──►│  ROUTE  │──►│  TRANSFORM │  │
│   └─────────┘   └─────────────┘   └─────────┘   └────────────┘  │
│        │               │               │              │         │
│        401              429             404            │         │
│        │               │               │              ▼         │
│        └───────────────┴───────────────┴──────► FORWARD          │
│                                                    │             │
│                                                    ▼             │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐                      │
│   │ User    │   │ Order   │   │ Notify  │  ← Microservices      │
│   │ Service │   │ Service │   │ Service │                       │
│   └─────────┘   └─────────┘   └─────────┘                       │
│                                                                  │
│   LOG: Every stage. Metrics. Tracing.                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Request enters. Auth: valid token? Rate limit: under quota? Route: which service? Transform: any changes? Forward: send to the right backend. Log: record it. Each stage can short-circuit. The pipeline is a filter. Only valid requests reach the services. The gateway protects your backends from bad traffic and bad actors. It's the first line of defense. And the last before your services see the traffic. Make it count.

---

## Real-World Examples (2-3)

**Kong.** Open-source API gateway. Plugin architecture. Auth, rate limiting, logging as plugins. Self-hosted or Kong Cloud. Used by startups and enterprises. The gateway you can own. Full control. Full responsibility.

**AWS API Gateway.** Fully managed. No servers. Integrates with Lambda, HTTP backends. Pay per request. Scale automatically. The gateway you never think about. Trade control for convenience. For many teams, that trade is worth it.

**Stripe.** Their API is behind a gateway. Rate limits. API keys. Request logging. Versioning. When you call Stripe, you hit their gateway first. Every request. They've scaled to billions of API calls. The gateway is why. It's invisible to you. But it's there. Doing its job. Every. Single. Call.

---

## Let's Think Together

**"You add a new microservice. What changes in the API gateway? Just routing? Or more?"**

Routing for sure. New route: /analytics → Analytics Service. But maybe more. New auth? If the service has different permissions. New rate limits? If it's expensive. New transformation? If the API shape is different. Documentation? OpenAPI spec update. The gateway is the contract. New service = new contract. It's not just a config change. It's a deployment. Version the gateway. Test the pipeline. A new service is never "just add a route." It's "update the gateway to include this service in the ecosystem." Treat it that way. Your future self debugging at 2 AM will thank you.

---

## What Could Go Wrong? (Mini Disaster Story)

A company deploys a new route. /admin → Admin Service. Forgot to add auth. The route was supposed to be internal. Someone found it. No auth. Full admin access. Data breach. Users affected. Headlines. The gateway had auth for other routes. This one slipped through. Default deny. Every new route must explicitly get auth. No route is public by accident. The gateway is your first line of defense. One misconfiguration. Everything exposed. Gateway config is security config. Treat it like production secrets. Review every change. No exceptions.

---

## Surprising Truth / Fun Fact

API gateways can become single points of failure. If the gateway goes down, all APIs are down. That's why Netflix, Uber run multiple gateway instances. Load balanced. Stateless. Any instance can handle any request. The gateway must be more reliable than the services behind it. Because when it fails, everything fails. Design for gateway resilience. Health checks. Circuit breakers. Fail fast. Don't let a sick gateway take down the whole system. Redundancy isn't optional. It's table stakes for production.

---

## Quick Recap (5 bullets)

- **Gateway = single entry point.** Pipeline: Auth → Rate Limit → Route → Transform → Forward → Log.
- **Components:** Router, auth, rate limiter, transformer, circuit breaker, logging.
- **New service = update routing, maybe auth, maybe rate limits.** Not just a config tweak.
- **Popular:** Kong, AWS API Gateway, Nginx, Envoy.
- **Gateway down = everything down.** Design for resilience. Stateless. Multiple instances.

---

## One-Liner to Remember

**An API gateway is an airport security pipeline for your APIs—auth, rate limit, route, transform, forward. Every request. Every time.**

---

## Next Video

Next: API versioning, blue-green deployments at the gateway, and when to split gateways. Scaling the entrance.
