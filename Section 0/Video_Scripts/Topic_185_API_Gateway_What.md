# API Gateway: What It Does

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A hotel concierge. Guest asks for a restaurant recommendation. Room service. A taxi. Laundry. The concierge routes each request to the right department. Kitchen. Front desk. Transportation. Housekeeping. The guest doesn't need to know which department handles what. One point of contact. That's an API gateway. The concierge between clients and your microservices.

---

## The Story

An API gateway is a single entry point for all client requests. Mobile app, web app, partner API—they all hit the gateway. The gateway routes to the right backend service. Order request? Route to order service. User profile? Route to user service. Search? Route to search service. Clients don't call services directly. They call the gateway. One URL. One place to manage.

Why? Without a gateway, clients need to know every service's address. Order service at api.orders.com. User service at api.users.com. Search at api.search.com. Every client configures multiple endpoints. Add a service? Update all clients. Change a URL? Update all clients. Nightmare. With a gateway: one URL. api.mycompany.com/orders, /users, /search. Gateway maps paths to services. Clients stay simple.

The gateway does more than route. It can authenticate (is this a valid token?). Rate limit (slow down this client). Transform (aggregate multiple service calls into one response). Cache. Log. The gateway is the bouncer, the traffic cop, and the receptionist—all in one.

---

## Another Way to See It

Think of an airport. Many flights. Many destinations. You don't go directly to the plane. You go to the terminal. Check-in. Security. Boarding. The terminal (gateway) is the single entry. It directs you. Checks your ticket (auth). Manages the flow (rate limit). Routes you to the right gate (service). One building. Many destinations.

Or a receptionist at a company. Callers don't get transferred to 50 extensions. They call main number. Receptionist routes: "Sales? Hold. Engineering? Hold." One number. Central control.

---

## Connecting to Software

Technically, an API gateway is a reverse proxy with routing logic. Nginx, Kong, AWS API Gateway, Azure API Management. You define routes: /api/orders/* → order-service:8080. /api/users/* → user-service:8081. Clients hit gateway. Gateway forwards to backend. Backends can be internal. Clients never see them.

The gateway hides your internal structure. You can rename services, change ports, split services—clients don't care. The gateway contract stays stable.

**Versioning:** API v1 at /v1/orders. API v2 at /v2/orders. Gateway routes by path. Old clients stay on v1. New clients use v2. Backend can run both versions. Or deprecate v1 gradually. Gateway is the versioning layer. One place to manage the transition.

**BFF (Backend for Frontend):** Gateway can aggregate. Mobile needs a different response shape than web. Gateway calls multiple services, assembles one response. "Order details + user info + recommendations" in one call. Mobile gets one round trip. Gateway does the composition. Reduces client complexity and latency.

**Caching:** Gateway can cache responses. GET /products?category=electronics. Cache for 60 seconds. Repeat requests served from cache. Reduces load on backend. Invalidate on write. Cache by path, query params, or headers. Gateway is the right place for edge caching. Fast for users. Relief for services. Combine with CDN: cache at the edge, close to users. Gateway and CDN work together for global, low-latency APIs. The gateway is your API's front door. Design it well. It shapes the entire client experience. Choose your gateway carefully: open source (Kong, Traefik) vs managed (AWS API Gateway, Azure). Trade-offs in cost, flexibility, and operations. Invest in your gateway—it is the face of your API.

---

## Let's Walk Through the Diagram

```
    WITHOUT GATEWAY (Clients Coupled to Services)     WITH GATEWAY (Single Entry)

    Mobile ──► Order Service                         Mobile ──┐
    Mobile ──► User Service                           Web   ──┼──► [API Gateway] ──► Order Service
    Mobile ──► Search Service                         Partner ─┘         │
                                                                         ├──► User Service
    Web   ──► Order Service                                               ├──► Search Service
    Web   ──► User Service                                                └──► Payment Service
    ...
    Every client knows every service.                   One entry. Gateway routes. Clients stay simple.
```

---

## Real-World Examples (2-3)

**Example 1: Netflix.** API gateway (Zuul, now their own) in front of hundreds of microservices. All device clients (TV, phone, web) hit the gateway. Gateway routes to catalog, playback, search, recommendations. They don't expose internal services. Security. Simplification.

**Example 2: Stripe.** Stripe API is one URL: api.stripe.com. Behind it: many services. Payments, subscriptions, customers, etc. Clients don't care. Gateway routes by path. /v1/charges, /v1/customers. Clean. Versioned. One contract.

**Example 3: E-commerce app.** Mobile app hits api.shop.com. /products, /cart, /orders. Gateway routes to product service, cart service, order service. Add a new "recommendations" service? Add route. No app update. Gateway abstraction.

---

## Let's Think Together

**Is API gateway the same as load balancer?**

Related but different. Load balancer distributes requests across instances of the *same* service. API gateway routes to *different* services by path, method, header. A gateway often includes load balancing—route to order service, and LB picks an order-service instance. But gateway = routing + auth + rate limit + more. LB = just distribution.

**Should every request go through the gateway?**

Usually yes for external clients. Internal service-to-service? Debatable. Some use gateway for everything. Some use service mesh for internal, gateway only for edge. Depends. Gateway adds latency. One hop. Often acceptable for the benefits.

---

## What Could Go Wrong? (Mini Disaster Story)

A company puts the API gateway in a single region. One point of failure. Gateway goes down. All clients broken. No one reaches any service. Lesson: gateway must be highly available. Multi-region. Multiple instances. Health checks. Gateway is critical path. Design for its failure too.

---

## Surprising Truth / Fun Fact

The term "API gateway" gained traction around 2015 with the rise of microservices. Before that, monoliths didn't need it—one app, one entry. Microservices created the need: many services, one front door. Kong, AWS API Gateway, and others rode that wave. Now it's standard for any API-backed system.

---

## Quick Recap (5 bullets)

- **API gateway** = single entry point for all client requests to your backend services.
- Routes requests to the right service by path, method, or other rules. Clients need one URL, not many.
- Hides internal architecture. Rename services, change structure—clients unaffected.
- Can add: authentication, rate limiting, caching, logging, transformation. Not just routing.
- Must be highly available. Gateway down = nothing works. Multi-instance, multi-region.

---

## One-Liner to Remember

API gateway = hotel concierge. One front door. Routes every request to the right department. Clients never need the internal map.

---

## Next Video

Next up: **API Gateway: Auth, Rate Limit, Route, Proxy**—the airport security checkpoint. All checks in one place before you board.
