# API Gateway at Scale: Rate Limit Layers

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A concert venue. 50,000 people. Multiple entrances. Each entrance has checkpoints. Gate 1: check ticket. Gate 2: search for weapons. Gate 3: count people entering. Gate 4: direct to the right section. At scale—10 entrances—each has all 4 gates. But Gate 3, the people counter, must coordinate ACROSS all 10 entrances. The venue capacity is 50,000. Not 50,000 per entrance. Total. That's multi-layer rate limiting at scale. Let's break it down.

---

## The Story

Rate limiting protects your system. "No more than 100 requests per minute per user." Simple. But at scale, rate limits live at multiple layers. The edge. The API gateway. Each backend service. Each layer has a different job. Edge: stop DDoS before it reaches you. Cheap. Fast. Coarse. Gateway: per-user, per-API-key limits. More granular. More expensive. Service: per-endpoint capacity. "This endpoint can handle 1000 QPS." Defense in depth. If one layer fails, another catches it. But coordination is hard. 10 API gateway instances. Each does its own rate limiting? No. They must share state. "User X has made 50 requests." All 10 gateways need to know. Redis. Distributed counters. Consistency. That's the scale challenge. Not the algorithm. The shared state.

---

## Another Way to See It

Think of a castle. Outer wall: stops the army. Archers on the wall: per-unit. Inner gate: checks each person. Different layers. Different granularity. An attacker who gets past the outer wall still hits the inner gate. An attacker who gets past the inner gate still hits the inner guards. Layers. Rate limiting is the same. Edge stops bulk attacks. Gateway stops abusive users. Service stops overload. No single point of failure. No "if we just had one rate limit, we'd be fine." You need all of them.

---

## Connecting to Software

**Edge rate limit.** CDN. Cloudflare. AWS Shield. Before traffic hits your servers. Per-IP limits. "100 requests per minute per IP." Stops simple DDoS. Rotating IPs? Attacker gets around it. But for basic protection, it's cheap. And fast. Traffic never reaches your origin. Saves bandwidth. Saves cost. First line of defense. Deploy it. Always.

**Gateway rate limit.** API gateway. Kong, AWS API Gateway, Envoy. Per-user. Per-API-key. Redis-backed counters. "User X: 45 requests this minute. Allow? Yes." "User X: 101 requests. Allow? No." Distributed. All gateway instances share Redis. Consistency. Latency: Redis round-trip. 1-2ms. Acceptable. Scale: Redis must handle millions of reads/writes per second. Cluster it. Shard by user_id. This layer catches what edge misses. Stolen API keys. Abusive users. The "10% of users cause 90% of load" problem.

**Service-level rate limit.** Each microservice: "I can handle 500 QPS." Queue or reject beyond that. Protects the service. Even if gateway allows it, the service says no. Backpressure. 503. Retry-After. The service protects itself. Gateway can't know every service's capacity. Service does. Defense in depth.

**Infrastructure rate limit.** Global. "Entire system: 100K QPS." Circuit breaker. When you're at capacity, reject at the edge. Don't let traffic in to be rejected later. Fail fast. Save resources. The venue is full. Close the doors. Don't let people in to stand in line for nothing.

---

## Let's Walk Through the Diagram

```
RATE LIMIT LAYERS AT SCALE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   TRAFFIC                                                         │
│      │                                                            │
│      ▼                                                            │
│   LAYER 1: EDGE (Cloudflare, CDN)                               │
│   Per-IP limit. Stops DDoS. Traffic never hits origin.            │
│      │                                                            │
│      ▼                                                            │
│   LAYER 2: API GATEWAY (Kong, Envoy)                             │
│   Per-user, per-API-key. Redis-backed. All instances share state. │
│      │                                                            │
│      ├────────► Redis (distributed counters)                      │
│      │                                                            │
│      ▼                                                            │
│   LAYER 3: SERVICES                                               │
│   Each service: own capacity limit. 503 when overloaded.          │
│      │                                                            │
│      ▼                                                            │
│   LAYER 4: GLOBAL (optional)                                     │
│   Circuit breaker. System at capacity? Reject at edge.             │
│                                                                  │
│   COORDINATION: Gateway instances → shared Redis. Consistency.    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Traffic hits the edge. Edge rate limits per IP. Bulk attack? Stopped. Legitimate traffic passes. Hits API gateway. Gateway checks per-user limit in Redis. Over limit? 429. Under limit? Pass to service. Service has its own capacity. Overloaded? 503. Each layer does its job. The diagram shows the stack. Edge is coarse. Gateway is granular. Service is specific. Together, they protect you. At scale, the hard part is Redis. Millions of keys. Millions of increments. Design for it.

---

## Real-World Examples (2-3)

**Stripe.** API rate limits per API key. Tiered: free tier, paid tier. Different limits. Enforced at gateway. Redis for counters. They document limits clearly. Users know what to expect. The system handles millions of requests. Rate limiting is invisible until you hit it. That's good design.

**Twilio.** Similar. Per-account limits. Protect their infrastructure. Abusive account? Throttled. Fair use for everyone else. Edge + gateway layers. Proven at scale.

**GitHub.** API rate limit: 5,000 requests per hour (authenticated). Enforced at API gateway. Clear headers: X-RateLimit-Remaining. Users can see where they stand. Transparency builds trust. Rate limiting doesn't have to feel hostile. It can be communicative.

---

## Let's Think Together

**"Attacker bypasses CDN rate limit with rotating IPs. Gateway catches per-user limit. What if the attacker uses stolen API keys?"**

Per-user limits help. But if the attacker has 10,000 stolen API keys, they get 10,000 × limit. Still a lot. Mitigations: detect anomalous key usage. "This key never made requests from Asia. Suddenly 10K from Asia." Flag it. Revoke. Rate limit per key AND per IP. "Same key from 1000 IPs?" Bot pattern. Block. Behavioral analysis. Not just counters. Anomaly detection. Rate limiting is necessary. Not sufficient. Combine with fraud detection. Abuse detection. Keys get stolen. Design for it. Revocation. Rotation. Monitoring. Defense in depth means more than multiple rate limit layers. It means multiple kinds of defense.

---

## What Could Go Wrong? (Mini Disaster Story)

A company launches a public API. Rate limit: 1000 requests per minute per key. Gateway uses Redis. Single Redis instance. Launch day. Traffic spikes. Redis becomes bottleneck. Latency: 50ms per rate limit check. Gateway timeouts. Requests fail. Users see 504. "Our API is down." It wasn't down. Rate limit check was slow. Fix: Redis cluster. Or local cache with periodic sync to Redis. Reduce Redis load. Pre-warm counters. The rate limit protected the backend. But the rate limit itself became the failure. Irony. Lesson: rate limit infrastructure must scale too. It's in the hot path. Every request touches it. Design accordingly. Redis is critical path. Don't make it a single point of failure.

---

## Surprising Truth / Fun Fact

Sliding window rate limiting is trickier than fixed window. Fixed: "100 requests per minute." Reset at minute boundary. User makes 100 at 0:59, 100 at 1:00. 200 in 1 second. Burst. Sliding window: "100 requests per any 60-second window." Smoother. Fairer. But harder to implement. Requires storing timestamps. Or approximate with Redis and Lua scripts. Many systems use fixed window because it's simpler. Good enough for most cases. When you need stricter fairness, sliding window. Know the tradeoff. Simplicity vs precision.

---

## Quick Recap (5 bullets)

- **Layers:** Edge (per-IP), Gateway (per-user/key), Service (per-endpoint), Global (capacity). Defense in depth.
- **Edge:** Cloudflare, CDN. Stops DDoS. Cheap. Fast. Coarse. Deploy first.
- **Gateway:** Redis-backed counters. Per-user limits. All instances share state. Coordinate.
- **Service:** Each service enforces own capacity. Backpressure. 503. Protects itself.
- **Scale challenge:** Redis must handle gateway load. Cluster. Shard. Rate limit infra is critical path.

---

## One-Liner to Remember

**Rate limiting at scale is a castle with multiple walls—edge stops the army, gateway checks each visitor, and services guard the inner rooms.**

---

## Next Video

Next: backpressure, circuit breakers, and what happens when backends are overwhelmed at the gateway.
