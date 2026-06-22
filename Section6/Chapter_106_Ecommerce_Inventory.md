# Chapter 95: E-Commerce / Inventory — Amazon / Shopify / Flash Sales

> Flash sales are the stress test of e-commerce. 10 million users hit "Buy Now"
> simultaneously for 100,000 units. Oversell by 1 unit and you have a PR crisis.
> Undersell and you left money on the table. Distributed inventory at scale is
> one of the hardest consistency problems in production systems.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

E-commerce system design comes up at Amazon (almost every interview), Shopify,
Instacart, Walmart, Target, and any company with physical inventory. The unique
challenges: distributed inventory with strong consistency guarantees, cart +
checkout as a multi-step saga, catalog at petabyte scale, and flash sale traffic
spikes that dwarf normal load by 100x.

---

## Planned Content

### Part 1: The Problem Space
- Catalog: millions of products, petabytes of images, search + filtering
- Inventory: real-time stock counts, multi-warehouse, reservations vs. purchases
- Cart: session state, price locks, expiry
- Checkout: payment + inventory decrement as an atomic saga
- Flash sales: 10M concurrent users, 100K units, must not oversell

### Part 2: Product Catalog
- Scale: Amazon has 350M+ products
- Storage: product metadata in DynamoDB/Cassandra, images in S3/CDN
- Search: Elasticsearch for full-text + faceted filtering (category, price, rating)
- Variants: one product → many SKUs (size S/M/L × color red/blue = 6 SKUs)
- Content delivery: product images via CDN, ~99% cache hit rate

### Part 3: Inventory Management
- The core problem: inventory count is shared mutable state
- Naive approach: `UPDATE inventory SET count = count - 1 WHERE sku_id = X AND count > 0`
  — works on one DB, breaks across shards
- Reservation pattern: reserve → confirm/cancel (two-phase)
  - Reserve: decrement available, create reservation record (TTL: 15 min)
  - Confirm: convert reservation to purchase on payment success
  - Cancel: release reservation on payment failure or timeout
- Multi-warehouse: which warehouse fulfills this order? (proximity, stock level)
- Eventual consistency acceptable for display ("only 3 left!") but not for purchase

### Part 4: Flash Sale Architecture
- Pre-sale: cache product/inventory data, pre-warm CDN, disable non-essential features
- Queue-based throttling: put all purchase requests in a queue, process at sustainable rate
- Token bucket: issue "purchase tokens" at a fixed rate = inventory drain rate
- Redis atomic decrement: `DECR inventory:sku:12345` — atomic, fast, no oversell
- Virtual waiting room: show users a queue position, rate-limit entry to checkout
- Real incident: Amazon Prime Day 2018 — dog food page went viral, took down
  parts of Amazon.com for 90 minutes due to unthrottled traffic

### Part 5: Shopping Cart
- Options: client-side (cookie/localStorage) vs. server-side (Redis/DB)
- Server-side cart: required for cross-device sync, price validation, inventory check
- Cart TTL: expire abandoned carts after 30 days
- Price lock: cart price = price at time of add-to-cart? or price at checkout?
  (Amazon: price at checkout; some retailers lock price for 15 min)
- Cart merger: user adds items as guest, then logs in → merge guest cart with account cart

### Part 6: Checkout as a Saga
- Steps: validate cart → reserve inventory → charge payment → confirm inventory →
  create order → send confirmation email
- Each step can fail: saga pattern with compensating transactions
  - Payment fails → release inventory reservation
  - Inventory confirm fails → refund payment
- Idempotency: checkout retries must not double-charge or double-reserve
- Distributed transaction alternative: outbox pattern + event-driven saga

### Part 7: Order Management
- Order states: pending → confirmed → processing → shipped → delivered → returned
- Order history: read-heavy, append-only — event sourcing fits well
- Returns and refunds: reverse saga (restock inventory + refund payment)
- Fraud check: integrated at checkout (see Ch94)

### Part 8: Interview Framework
- Always separate: catalog (read-heavy, CDN) vs. inventory (consistency-critical) vs.
  cart (session state) vs. checkout (saga)
- Key decision: how to handle inventory — reservation pattern vs. Redis atomic ops
- Flash sale special case: always mention queue + token bucket + virtual waiting room
- L5 vs. L6: L5 draws a checkout flow; L6 explains the saga pattern with compensating
  transactions, why Redis DECR prevents oversell, and how the virtual waiting room
  protects downstream services

---

## The One-Sentence Summary

> "E-commerce = catalog (CDN + Elasticsearch) + inventory (reservation pattern or Redis atomic ops for consistency) + cart (server-side with TTL) + checkout (saga with compensating transactions) — flash sales add a queue + token bucket layer that throttles purchase rate to match inventory drain rate."

---

*Full chapter: ~2,500 lines. Pairs with Ch70 (Payment Systems) and Ch94 (Fraud Detection).*
