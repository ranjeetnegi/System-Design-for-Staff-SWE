# Request Flow: From User to DB and Back

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You tap "Order Now" on a food delivery app. That single tap triggers a journey. Your phone → internet → DNS → CDN or load balancer → API gateway → authentication → order service → payment service → database → notification service → driver matching. All of that. Then the response flows back. "Order Confirmed!" on your screen. One tap. Ten steps. Each step can fail. Each step can be slow. Let me trace the entire journey—and show you where it breaks.

---

## The Story

A request doesn't magically reach your server. It travels. Step by step. Layer by layer. Imagine the food delivery tap. You tap. Your phone has the request. Where does it go? First: the network. Your phone sends packets. Through WiFi or cellular. To the internet. The request needs an IP address. The app knows "api.foodapp.com." Not an IP. So step 2: DNS. Resolve the domain. "api.foodapp.com" → "203.0.113.42". Now we have an address. Step 3: The request hits a load balancer. One of many. It distributes traffic across servers. Picks server 7. Step 4: API gateway. Authenticates you. Rate limits. Routes to the right service. Step 5: Order service. Your code. Creates the order. Calls payment service. Step 6: Payment service. Charges the card. Step 7: Database. Persists the order. Step 8: Notification service. Sends "Order confirmed!" to your phone. Step 9: Driver matching. Finds a driver. Step 10: Response. Flows back. Through every layer. To your phone. "Order Confirmed!" Each step adds latency. Each can fail. DNS timeout. Load balancer down. Auth failure. Payment declined. Database slow. Network drop. When a user says "the app is slow," the bottleneck could be any of these. You need to know the path. Trace it. Find it. Fix it.

---

## Another Way to See It

Think of a letter. You drop it in a mailbox. It goes to the post office. Sorted. Truck. Airport. Another post office. Mail carrier. Recipient's mailbox. Many hops. One gets stuck—the whole letter is delayed. Or a package. Warehouse. Truck. Sorting center. Plane. Customs. Another truck. Your door. Each step tracked. Each step a potential delay. Same with a request. Trace the path. Find the bottleneck. The chain is only as strong as the weakest link.

---

## Connecting to Software

**Full flow—every step:** (1) Client—your phone or browser initiates. (2) DNS—resolve api.example.com to IP. (3) Load Balancer—spread traffic across servers. (4) API Gateway—authenticate, rate limit, route. (5) Application Server—business logic runs. (6) Cache—check Redis for hot data. (7) Database—if cache miss, fetch from DB. (8) Response—retraces the path. Back through cache, app, gateway, LB, to client.

**Each step can fail:** DNS: wrong IP, timeout, DNS outage. LB: overloaded, misconfigured, unhealthy targets. Gateway: auth failed, rate limited, wrong route. App: bug, OOM, slow code. Cache: miss, connection failed, eviction. DB: slow query, connection pool exhausted, disk full. Network: packet loss, latency, partition. The chain is only as strong as the weakest link. And the slowest step sets the total latency. If DNS takes 2 seconds, nothing else matters. If DB takes 5 seconds, the user waits 5+ seconds. Trace. Measure. Fix the slowest. Then the next.

---

## Let's Walk Through the Diagram

```
    REQUEST FLOW: ONE TAP, MANY STEPS (Detailed)

    USER taps "Order" 
      │
      │  [1] Client (phone/browser) - assembles request
      ▼
    [2] DNS - resolve api.foodapp.com → IP (can fail: timeout)
      │
      ▼
    [3] Load Balancer - pick server (can fail: all servers down)
      │
      ▼
    [4] API Gateway - auth, rate limit, route (can fail: 401, 429)
      │
      ▼
    [5] Application Server - order service (can fail: bug, OOM)
      │
      ├──► [6] Cache (Redis) ──► HIT? Return (can fail: miss, timeout)
      │
      └──► [7] Database (if miss) (can fail: slow query, pool full)
      │
      ▼
    [8] Response flows back: DB → Cache → App → Gateway → LB → Client

    Each step: potential latency, potential failure.
    The slowest step = your bottleneck.
```

Number the steps. Trace a real request. Measure each. DNS: 5ms. LB: 2ms. Gateway: 10ms. App: 50ms. Cache: 1ms. DB: 2000ms. The database is the problem. 2 seconds. Fix the query. Add index. Or cache. The diagram shows the path. Tracing shows the numbers. Both matter.

---

## Real-World Examples (2-3)

**Example 1: E-commerce checkout.** User clicks "Buy." Request hits CDN (static assets from edge). API (auth, validate cart). Order service (create order). Payment service (charge card). Inventory service (reserve stock). Database (persist). Notification (email). Response. Any slow service = slow checkout. Payment and inventory are often the bottlenecks. Measure. Optimize those first.

**Example 2: Social feed.** User opens app. Request: auth, fetch follow list, fetch posts for each follow, rank, return. Cache at each layer. Timeline service. Post service. User service. Multiple downstream calls. N+1 or fan-out? Design matters. Latency adds up. Cache aggressively. Parallelize. One request. Many downstream. Trace the tree.

**Example 3: Search.** User types query. Request: gateway, search service, cache (recent queries?), index (Elasticsearch), rank, return. Cache hits: fast. Cache miss + slow index: slow. The index is often the bottleneck. Optimize queries. Add caching. CDN for popular searches.

---

## Let's Think Together

User says "the app is slow." Which step is the bottleneck? How do you find out?

Add tracing. Distributed tracing—OpenTelemetry, Jaeger, Zipkin. Each request gets an ID. It passes through every layer. You see: DNS 5ms, LB 2ms, Gateway 10ms, App 50ms, Cache 1ms, DB 2000ms. The database is the problem. 2 seconds. Fix the query. Add index. Or cache. Without tracing, you're guessing. "Maybe the app?" "Maybe the network?" Tracing tells you. Measure. Then optimize. You can't fix what you can't measure. Tracing is your map. Add it. Before you need it. When you need it, you'll have the data.

---

## What Could Go Wrong? (Mini Disaster Story)

A team launches a new feature. "View order history." It works in testing. Production: users report 10-second loads. Why? The feature makes 1 request. But that request triggers 50 database queries. One per order. N+1 problem. No caching. The database is overwhelmed. One "simple" feature. One bad code path. Total latency: 10 seconds. They add tracing. They see: 50 sequential DB calls. Each 200ms. 10 seconds total. Fix: batch the query. One query. 100ms. Problem solved. The lesson: understand the request flow. One request can spawn many. Each spawn adds latency. Trace it. Optimize the hot path. What looks like one request can be 50. Find those. Fix those.

---

## Surprising Truth / Fun Fact

Google measures latency at every layer. They have a culture of "every millisecond matters." Their search latency budget is split: so many ms for network, so many for backend, so many for rendering. They know exactly where time goes. Most companies don't. They deploy. It's "slow." They don't know where. Add tracing. Make the invisible visible. Once you see the flow, you can fix it.

---

## Quick Recap (5 bullets)

- **Request flow:** Client → DNS → LB → API Gateway → App → Cache → DB → back.
- **Each step** can add latency and can fail. The slowest step sets total latency.
- **Tracing** (OpenTelemetry, Jaeger) shows where time goes. Measure before optimizing.
- **One request** can spawn many (N+1, fan-out). Trace the full tree. Fix the hot path.
- **When "slow":** add tracing. Find the bottleneck. Don't guess.

---

## One-Liner to Remember

**One tap. Ten steps. Trace the path. Find the bottleneck. Fix it.**

---

## Next Video

Next: **Sync vs. async design.** The waiter who stands and watches the chef. Or the one who keeps taking orders. When to use which? See you there.
