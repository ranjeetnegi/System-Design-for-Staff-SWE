# Request IDs and Tracing: Why They Matter

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A patient visits a hospital. Gets a wristband with ID: "P-2024-5678." Doctor writes it on the prescription. Lab technician writes it on the blood test. Pharmacist writes it on the medicines. If anything goes wrong, you trace back using that ID. "What happened to patient P-2024-5678?" Every step is linked. In software: a request enters your system and passes through 10 microservices. Without a request ID, debugging is like finding a needle in a haystack of millions of logs.

---

## The Story

A patient arrives at a hospital. Registration. Wristband. ID: "P-2024-5678."

Doctor sees the patient. Writes P-2024-5678 on the prescription. Lab draws blood. Writes P-2024-5678 on the vial. Pharmacist dispenses medicine. Writes P-2024-5678 on the bag.

Two days later. Something went wrong. "What happened to patient P-2024-5678?" You search. Prescription. Lab report. Pharmacy records. All linked by that ID. You trace the entire journey. Find the issue. Fix it.

Without the ID? "Some patient had an issue. We're not sure which." Thousands of patients. No way to find the right records. Chaos.

Software is the same. One request. Ten microservices. Auth. API gateway. User service. Order service. Payment service. Notification service. Each logs. Millions of log lines per minute. "A payment failed." Which one? Which request? Without a request ID, you're lost.

---

## Another Way to See It

A parcel. Tracking number: 1Z999AA10123456784. It moves. Post office. Sorting center. Truck. Delivery. Every scan logs that number. You check the tracking. See the full journey. Delayed at sorting center? You know. Lost? You can trace where.

A request ID is your request's tracking number. Same idea. Every service logs it. You trace the journey.

---

## Connecting to Software

**Request ID** = unique identifier (usually UUID) generated when a request enters the system.

**Flow:**
1. Request hits API gateway or load balancer.
2. No ID? Generate one. `X-Request-ID: 550e8400-e29b-41d4-a716-446655440000`
3. Pass to every downstream service via headers.
4. Every log line includes the request ID.
5. User reports issue: "My payment failed 10 minutes ago." You have their request ID (from error page or support). Grep logs: `grep 550e8400-e29b-41d4-a716-446655440000 /var/log/*.log`. See the entire journey. Auth. Order. Payment. Where it failed. Why.

**Distributed tracing** (OpenTelemetry, Jaeger, Zipkin): Goes further. Not just ID, but:
- Spans: each service call is a "span" with timing.
- Parent-child: span for "process order" contains span for "charge payment."
- Service map: visualize which services talked to which.
- Latency breakdown: "Payment service took 3 seconds. Why?"

**Correlation ID** = similar. Sometimes used for business transactions spanning multiple requests. "Order #456" might have multiple API calls. Correlation ID links them.

---

## Let's Walk Through the Diagram

```
Request flow with Request ID:

  User Request
       │
       ▼  Generate: X-Request-ID: abc-123
  ┌─────────────┐
  │ API Gateway │  log: [abc-123] Request received
  └──────┬──────┘
         │  Forward header
         ▼
  ┌─────────────┐
  │ Auth Svc    │  log: [abc-123] User authenticated
  └──────┬──────┘
         │  Forward header
         ▼
  ┌─────────────┐
  │ Order Svc   │  log: [abc-123] Creating order
  └──────┬──────┘
         │  Forward header
         ▼
  ┌─────────────┐
  │ Payment Svc │  log: [abc-123] ERROR: Card declined
  └─────────────┘

  Debug: grep "abc-123" → See full journey. Payment failed. Card declined.
```

---

## Real-World Examples

**1. E-commerce checkout**  
User pays. Fails. Error page: "Request ID: abc-123. Contact support with this ID." User contacts support. Support searches logs for abc-123. Sees: auth OK, order created, payment failed at Stripe—insufficient funds. Support explains. User adds money. Retries. Request ID turned a "something failed" into a 30-second diagnosis.

**2. Microservices debugging**  
Order service slow. Is it us or payment service? Trace shows: order service 50ms. Payment service 4 seconds. Payment is the bottleneck. Fix payment. Request ID + tracing found it.

**3. Uber**  
Uber has 4,000+ microservices. A ride request touches dozens. Without distributed tracing, debugging would be impossible. Their tracing system processes 150 million traces per day. Request IDs and spans are the backbone.

---

## Let's Think Together

User reports: "My payment failed 10 minutes ago." Fifty million requests in that window. How do you find their request?

Pause. Think.

Option 1: Return request ID in the error response. "If payment fails, show Request ID on the error page." User copies it. Support greps. Found. Option 2: If no request ID, use user ID + timestamp. Search logs for that user around that time. Slower. Option 3: Structured logging. Every log has user_id, request_id, timestamp. Filter by user_id and time range. Still need request_id to get the exact request. Best practice: always return request ID on errors. Make it visible. "Something went wrong. Reference: abc-123." Support's best friend.

---

## What Could Go Wrong? (Mini Disaster Story)

A company. No request IDs. Production issue. "Some users can't checkout." Logs: millions of lines. No way to correlate. Engineers guessed. "Maybe it's payment?" Check payment logs. Overwhelming. "Maybe it's inventory?" Same. Hours of grep. No clear path. They added request IDs. Next incident: user reported with ID. Grep. Found in 10 seconds. Payment timeout. Fixed. Request IDs turned chaos into clarity. Don't ship without them.

---

## Surprising Truth / Fun Fact

Uber's distributed tracing system processes 150 million traces per day. Without request IDs and tracing, debugging their 4,000+ microservices would be impossible. One request. Dozens of services. One trace. Full visibility. That's the power of request IDs taken to the extreme. Even in a smaller system—monolith or a handful of services—request IDs pay off. The first time you grep for a request ID and trace a user's full journey in 10 seconds, you'll never want to debug without them again. Add them early. Pass them everywhere. Log them on every line. It's one of the highest ROI improvements you can make to your observability stack. Request IDs cost almost nothing to add. A few lines of code. A middleware. A header. But they transform debugging from "we have no idea" to "here's the exact request, here's the full journey." When production breaks at 2 AM, that difference matters. Add request IDs. You'll sleep better.

---

## Quick Recap (5 bullets)

- Request ID = unique ID (UUID) generated at entry, passed through every service via headers.
- Every log line should include the request ID. Grep = see the full journey.
- Return request ID to users on errors. "Reference: abc-123." Support can trace.
- Distributed tracing (OpenTelemetry, Jaeger): spans, timing, service map. Request ID is the root.
- Correlation ID links multiple requests for one business transaction (e.g., order).

---

## One-Liner to Remember

*Request ID is your request's tracking number—one grep and you see its entire journey across every service.*

---

## Next Video

That's our last topic in this section. You've covered caching, CDNs, APIs, and observability. Great foundation for system design. See you in the next section!
