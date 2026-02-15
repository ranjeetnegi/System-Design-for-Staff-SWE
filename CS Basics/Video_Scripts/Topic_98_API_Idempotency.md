# API Design: Idempotency for Write APIs

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You click "Pay Now." Slow network. You click again. And again. Three clicks. Without idempotency: three charges on your card. Rs 15,000 gone. With idempotency: the first click processes the payment. The second and third return the same result. Charged once. Safe. The internet is unreliable. Retries happen. Idempotency ensures retries don't create duplicates.

---

## The Story

You're checkout. Cart total: Rs 5,000. You click "Pay Now." Loading. Spinner. Nothing. Network slow. You click again. Still loading. Click again. Third time. Finally: "Payment successful."

How many times did you pay? Without idempotency: three. Rs 15,000 charged. Your money. Triple charge. Dispute. Refund. Headache.

With idempotency: one. First click processes. Second and third? Server says: "I've seen this before. Here's the same result." No duplicate charge. Safe.

The internet is unreliable. Networks timeout. Clients retry. Users double-click. Idempotency means: doing the same request multiple times has the same effect as doing it once. No duplicates. No extra charges. No duplicate orders.

---

## Another Way to See It

A light switch. Toggle. On. Toggle. Off. Toggle. On. Each toggle has one effect. Flipping it multiple times doesn't create multiple lights. It's idempotent. Deleting a file: delete once, it's gone. Delete again? Already gone. Same result. Idempotent. Creating an order: create once, you have one order. Create again? Without idempotency, you have two orders. Idempotency makes creation behave like toggling—same request, same outcome.

---

## Connecting to Software

**Idempotent** = performing an operation multiple times has the same effect as performing it once.

**Natural idempotency:**
- GET — Same request, same response. Idempotent.
- PUT — Replace resource. Same body, same result. Idempotent.
- DELETE — Delete once, gone. Delete again, already gone. Idempotent.

**POST is NOT idempotent.** Each POST can create a new resource. Submit form twice? Two records. That's the problem.

**Idempotency key:** Client generates a unique ID (e.g., UUID) for each logical operation. Sends it with the request. Header: `Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000`.

Server: "Have I seen this key before?"  
- No → Process request. Store result. Store key. Return result.  
- Yes → Return stored result. Do not process again.

**Implementation:** Store idempotency keys with results. In DB or Redis. TTL: 24 hours typical. Key format: idempotency_key + result + status. On retry: lookup key, return stored result. Don't reprocess. Don't charge again. Don't create duplicate orders. The storage cost is small. The protection is huge. For payment APIs, 24–72 hours is standard. Disputes can take days. Keep keys at least that long. After that, key expires. Same key later? Treated as new. Usually fine for payments—disputes have longer windows.

---

## Let's Walk Through the Diagram

```
Idempotency Flow:

  Client                          Server
     │                               │
     │  POST /payments                │
     │  Idempotency-Key: abc-123      │
     │──────────────────────────────►│
     │                               │ Check: seen abc-123?
     │                               │ No. Process payment.
     │                               │ Store: abc-123 → result
     │  ~~~~~~~~ Network timeout ~~~~~│
     │  (Client retries)              │
     │  POST /payments                │
     │  Idempotency-Key: abc-123      │
     │──────────────────────────────►│
     │                               │ Check: seen abc-123?
     │                               │ Yes! Return stored result
     │  Same result, no new charge ◄─│
```

---

## Real-World Examples

**1. Stripe**  
Every POST request requires `Idempotency-Key`. Payments. Subscriptions. Refunds. All of them. Stripe's documentation emphasizes it. Without it, retries could double-charge. With it, safe. Industry standard.

**2. Uber**  
Ride requests. Payment at end. Network can fail. Driver and rider both retry. Idempotency prevents duplicate charges. Same ride. One payment. Without it, a flaky network could charge a rider twice for one trip. Support tickets. Refunds. Lost trust. Idempotency keys are standard in ride-sharing and any high-value transaction.

**3. E-commerce checkout**  
Order creation. User clicks "Place order." Timeout. Clicks again. Idempotency key from client. First request creates order #456. Second request: "Order #456 already exists. Here it is." No duplicate orders.

---

## Let's Think Together

User retries POST /orders with the same idempotency key. Server already created order #456. What should the server return?

Pause. Think.

Return 200 OK. Same status as the first request. Body: order #456. Exactly what the first request returned. Don't create a new order. Don't return an error. The client thinks it might have been the first attempt. Give it the result. Same response. Idempotent. Client is happy. One order. No duplicates.

---

## What Could Go Wrong? (Mini Disaster Story)

A payment gateway. No idempotency. Merchant integrated. Customer paid. Network blip. Client retried. Second charge went through. Customer charged twice. Rs 10,000. Customer demanded refund. Merchant lost trust. Payment gateway blamed. They added idempotency. Now every payment request needs a key. Problem solved. But the incident cost them customers. Idempotency isn't optional for money. It's required. The same applies to order creation, subscription signups, and any operation that has real-world consequences. Users will retry. Networks will fail. Browsers will refresh. If your API isn't idempotent, you will create duplicates. Guaranteed. Add idempotency keys to every important POST. Make it a habit. Your future self will thank you when production is calm.

---

## Surprising Truth / Fun Fact

Stripe's API requires an Idempotency-Key header for all POST requests. Every serious payment API in the world uses this pattern. When money moves, retries are guaranteed. Idempotency is the shield. Without it, you're gambling with user funds.

---

## Quick Recap (5 bullets)

- Idempotent = same request multiple times = same effect as once. No duplicates.
- GET, PUT, DELETE are naturally idempotent. POST is not.
- Idempotency key: client sends unique ID. Server stores result by key. Retry returns stored result.
- Store keys with results. Expire after 24–72 hours. Don't store forever.
- For payments, orders, any write that affects money or critical state—use idempotency keys. Make it mandatory for those endpoints. Reject requests without a key. Return 400 Bad Request. Force clients to send it. You'll prevent so many production incidents. One duplicate charge can cost you a customer. One duplicate order can clog your fulfillment. Idempotency keys are cheap insurance. The implementation is simple: a table or Redis key, lookup before process, store result. A few hours of work. Prevents incidents that could cost days of debugging and lost revenue. Every payment API, every order API, every subscription API should use them. No exceptions. Once you've built idempotency into one API, the pattern is clear. Reuse it everywhere writes matter. Your payment service. Your order service. Your subscription service. Copy the middleware. Copy the storage logic. It's boilerplate that saves you from boilerplate bugs. Duplicate charges. Duplicate orders. Duplicate signups. All preventable with one pattern.

---

## One-Liner to Remember

*Idempotency keys turn "create" into "create once"—retries return the same result, never duplicates.*

---

## Next Video

Next: Evolving APIs. How to add fields, change structure, and migrate—without breaking clients. Topic 99: How to Evolve APIs Without Breaking Clients.
