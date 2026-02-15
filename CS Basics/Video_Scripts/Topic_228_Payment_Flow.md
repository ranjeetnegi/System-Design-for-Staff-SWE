# Payment Flow: ACID and Idempotency

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You buy a phone for Rs 50,000. Three things must happen: (1) Your account debited Rs 50,000. (2) Merchant account credited Rs 50,000. (3) Order marked as PAID. If ANY fails—you lose money, or the merchant doesn't get paid, or the order stays unpaid. Payment is where ACID and idempotency aren't academic. They're life or death for your business.

---

## The Story

A customer taps Pay. Behind the scenes: debit their account. Credit the merchant. Update the order status. Three operations. Three systems, maybe. If step 1 succeeds and step 2 fails—money left your account but never reached the merchant. Dispute. Refund. Trust broken. If step 2 succeeds and step 3 fails—merchant has the money, but your order still says "Pending." Customer confusion. Support tickets. "I paid! Where's my order?" The only acceptable outcome: all three happen, or none do. Atomicity. All or nothing. No partial states. Ever.

And then: the user double-clicks Pay. Network retry. Your server gets two "charge this card" requests. Without idempotency, you charge twice. Double the amount. Chargebacks. Angry customer. Idempotency: same request, same payment ID, same result. Charge once. Return the same response for duplicates. It's not optional. It's mandatory for money.

---

## Another Way to See It

Imagine a bank transfer. You move Rs 10,000 from Account A to B. The bank doesn't debit A and hope B gets it. It does both in one transaction. Debit A, credit B. One atomic unit. If the system crashes between debit and credit, the whole transaction rolls back. You never see "money left my account but didn't arrive." Same for payments. One logical transaction. Multiple steps. One outcome. The bank gets this right. So must you.

---

## Connecting to Software

**Atomicity.** Debit + credit + order update = one transaction. Use a database transaction. All three writes in one BEGIN...COMMIT. Any failure? ROLLBACK. All or nothing. If they're in different systems (your DB vs payment gateway), use sagas or two-phase commit. Complex. But atomicity is non-negotiable for money. Users trust you with their funds. Honor that trust.

**Idempotency.** Client sends payment request with idempotency_key: "order_12345_pay". Server: "Have I seen this key?" No → process payment, store key with result. Yes → return stored result. No second charge. Handle double-clicks. Handle retries. Handle webhook duplicates. Same key, same response. Every payment gateway supports this. Use it.

**Flow.** User → Checkout → Payment Service → Payment Gateway (Stripe, Razorpay) → Bank. Gateway processes. Returns async. Webhook: "Payment succeeded." Your server: update order to PAID. The gateway responds asynchronously. You show "Processing..." then update on confirmation. Never assume sync. Gateways are async. Design for it. Your users will wait. Your system must not assume.

**Webhook handling.** Stripe sends "payment_intent.succeeded." Your server updates order. Crashes before responding 200. Stripe retries. Same webhook. Idempotency: "Payment X already processed? Return 200, do nothing." Don't process twice. Don't update order twice. Store webhook IDs. Deduplicate. This happens. Plan for it. Every production payment system sees duplicate webhooks.

---

## Let's Walk Through the Diagram

```
PAYMENT FLOW - ACID AND IDEMPOTENCY
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   USER          CHECKOUT        PAYMENT SVC      GATEWAY         │
│                                                                  │
│   [Pay] ──► idempotency_key ──► Check: seen?                    │
│                    │                    │                         │
│                    │              No → Process ──► Stripe/Razorpay│
│                    │                    │                │       │
│                    │                    │                ▼       │
│   [Processing] ◄───┘              ◄──── WEBHOOK ── Bank approves│
│                                         │                        │
│                                         ▼                        │
│                              BEGIN TRANSACTION                   │
│                                Debit user                        │
│                                Credit merchant                   │
│                                Order = PAID                      │
│                              COMMIT (all or nothing)             │
│                                                                  │
│   Idempotency: Same key = same response. No double charge.       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: User pays with idempotency key. Server checks. New? Process. Existing? Return cached result. Payment goes to gateway. Webhook returns success. One transaction: debit, credit, update order. Rollback on any failure. Webhook retries? Idempotent. Process once. The diagram shows the flow. The key insight: every step must be safe to repeat. Every step must succeed together or fail together.

---

## Real-World Examples (2-3)

**Stripe.** Idempotency keys on every request. Send the same key twice? Same response. No double charge. Webhooks with event IDs. Store them. Deduplicate. Industry standard. When you integrate Stripe, you get this for free. Use it.

**Razorpay (India).** Same pattern. Idempotency for API calls. Webhooks for async confirmation. Used by thousands of Indian startups. The principles are universal. The implementation is local. Money moves the same way everywhere.

**PayPal.** Older flow. But the principles hold. Async confirmation. Idempotency for duplicate prevention. Money moves. Get it right. The giants figured this out decades ago. Learn from them.

---

## Let's Think Together

**"Webhook from Stripe says 'payment successful.' Your server crashes before updating the order. Stripe retries. How do you handle?"**

Idempotency by webhook event ID. Store event_id when you process. "Payment succeeded for event evt_xyz." First attempt: process, update order, store evt_xyz. Crash. Stripe retries. Second attempt: "evt_xyz already processed? Return 200 OK. Don't process again." Stripe is happy. You didn't double-update. Orders stay correct. Always store webhook IDs. Always check before processing. One table. One query. Saves you every time. This isn't theoretical. It happens weekly in production. Be ready.

---

## What Could Go Wrong? (Mini Disaster Story)

A payments startup. No idempotency. User's network flickers. "Pay" request sent twice. Both processed. User charged Rs 50,000 twice. Rs 100,000 gone. Support floods. Refunds. Reputation damage. Legal letters. One idempotency_key in the API would have fixed it. "order_123_pay" — second request returns "already processed." Cost: one database lookup. Save: customer trust, money, lawyers, sleep. Payment systems demand idempotency. No shortcuts. No exceptions. The first bug will find you. Make sure you're ready.

---

## Surprising Truth / Fun Fact

Stripe's idempotency keys expire after 24 hours. Old keys are recycled. So don't reuse them across days. One payment per key. New payment, new key. The 24-hour window covers retries, network issues, double-clicks. After that, if you're retrying, something else is wrong. Generate a fresh key. Move on. The expiry isn't a limitation. It's a feature. Prevents key reuse bugs that could cause wrong charges.

---

## Quick Recap (5 bullets)

- **Atomicity:** Debit + credit + order update = one transaction. All or nothing.
- **Idempotency:** Same payment ID = same result. No double charge on retries or double-clicks.
- **Flow:** User → Payment Service → Gateway → Bank. Async webhook confirms success.
- **Webhook handling:** Store event IDs. Deduplicate. Return 200 even if already processed.
- **Never assume sync:** Payment gateways are async. Design for webhooks and retries.

---

## One-Liner to Remember

**Payment flow is a bank transfer—debit and credit in one transaction, and same request ID always means same outcome.**

---

## Next Video

Next: payment reconciliation, refunds, and handling partial failures. When things go wrong.
