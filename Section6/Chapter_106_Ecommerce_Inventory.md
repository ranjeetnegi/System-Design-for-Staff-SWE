# Chapter 106: E-Commerce & Inventory — Amazon / Shopify / Flash Sales

> Flash sales are the stress test of e-commerce. Ten million users hit "Buy Now"
> simultaneously for 100,000 units. Oversell by 1 unit and you have a PR crisis.
> Undersell and you left money on the table. Distributed inventory at scale is
> one of the hardest consistency problems in production engineering.

---

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        AT-A-GLANCE: E-Commerce System                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  PROBLEM        Design Amazon.com-scale product catalog, inventory, cart,    │
│                 checkout, and flash-sale infrastructure                       │
│                                                                              │
│  SCALE          500M products  ·  12M orders/day  ·  100K items/sec          │
│                 (flash sale)   ·  3M items sold/minute at Amazon peak         │
│                 Shopify: 75M requests in 30 min on Black Friday 2021          │
│                                                                              │
│  KEY COMPONENTS                                                              │
│    Product Catalog   — Elasticsearch + DynamoDB + S3/CDN                    │
│    Inventory         — Reservation pattern + Redis atomic DECR               │
│    Cart              — Redis (session) + PostgreSQL (persistent)             │
│    Checkout Saga     — Order → Payment → Inventory → Fulfillment            │
│    Flash Sale        — Virtual waiting room + queue + Lua atomic ops         │
│    Fulfillment       — Multi-warehouse routing + split shipments             │
│                                                                              │
│  KEY NUMBERS                                                                 │
│    Product metadata  ≈ 2 KB/product  →  500M × 2 KB = 1 TB metadata         │
│    Product images    ≈ 500 KB avg    →  500M × 500 KB = 250 TB images        │
│    Cart TTL          30 days (persistent)  ·  15 min (inventory hold)        │
│    Checkout latency  p99 < 2 sec, p50 < 800 ms                               │
│    Inventory read    < 10 ms (Redis cache), < 50 ms (DB fallback)            │
│    Flash sale TPS    100K inventory decrements/sec peak                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Why This Chapter Matters

E-commerce system design appears at Amazon (nearly every loop), Shopify, Instacart,
Walmart, Target, eBay, and any company with physical or digital inventory. The unique
challenge is that e-commerce sits at the intersection of three hard distributed-systems
problems at once: a read-heavy catalog (like a content system), strong-consistency
inventory (like a financial ledger), and multi-step transactional checkout (like a
payment saga). Candidates who know how to separate these concerns and address each
correctly are rare, and interviewers at Staff/L6 level probe all three in a single
session.

The flash sale scenario in particular is a forcing function: it exposes every weakness
in an architecture. Naive solutions oversell (disappointed customers, chargebacks) or
undersell (lost revenue). Correct solutions use Redis atomic operations, queue-based
throttling, and virtual waiting rooms — and the interviewer wants to hear you explain
exactly why, not just name-drop the technologies.

This chapter covers the complete system: product catalog at Amazon scale, the
reservation pattern for inventory, the Saga orchestration pattern for checkout,
multi-warehouse fulfillment routing, and flash sale architecture that served 100K
purchases per second without overselling a single unit.

---

## Part 1: The Problem Space — Four Distinct Systems

### 1.1 Decomposing "Design Amazon"

When an interviewer says "design Amazon" or "design an e-commerce platform," they are
asking you to design four fundamentally different systems that happen to live on the
same platform. Candidates who treat this as one monolithic problem will either run out
of time or produce a shallow design that does not survive follow-up questions. The
first thing you must do — out loud, in the interview — is decompose the problem.

**System A: Product Catalog (Read-Heavy, Eventual Consistency Acceptable)**

The catalog is a massive read-heavy system. At Amazon scale — over 350 million product
listings — the catalog is read billions of times per day but written to infrequently by
comparison. A product page view does not need perfect real-time accuracy: if a product
description is 30 seconds stale, no customer notices. This means caching aggressively,
using CDNs for images, and optimizing for read throughput and latency rather than write
consistency. Elasticsearch powers the search experience. DynamoDB or Cassandra stores
the product metadata. S3 stores the raw images, and a CDN like CloudFront caches them
globally with a 99% cache-hit rate.

**System B: Inventory (Write-Heavy, Strong Consistency Required)**

Inventory is the exact opposite of the catalog: it must be accurate. If the system says
there is 1 unit in stock and 1,000 users try to buy it simultaneously, exactly 1 user
should succeed and 999 should see "out of stock." Overselling — where 10 users each
successfully purchase the last unit — is a severe business failure. This means strong
consistency guarantees, atomic operations, and careful transactional semantics. The
inventory count is shared mutable state, and every distributed-systems risk (race
conditions, split-brain, network partitions) must be accounted for.

**System C: Cart and Session State (Session-Scoped, Availability Preferred)**

The shopping cart is a user-session-scoped data structure. It needs to survive browser
refreshes, support cross-device access, and handle the anonymous-to-authenticated
transition gracefully. Cart data has relaxed consistency requirements — if a cart
briefly shows stale pricing, that is acceptable — but it must be highly available.
Redis is the right primary store here because read/write latency must be under 1
millisecond and cart data is small and inherently key-value structured.

**System D: Checkout Saga (Transactional, Exactly-Once Required)**

Checkout is the most complex component because it crosses system boundaries. A single
checkout involves: reserving inventory, charging the payment method, confirming the
inventory deduction, creating an order record, and triggering fulfillment. Each step
can fail. The payment service is external. The inventory service is internal. If
payment succeeds but the inventory confirm fails, the customer was charged but won't
receive their item. Handling this correctly requires the Saga pattern with
compensating transactions — a distributed transaction substitute that provides
eventual consistency with well-defined failure recovery.

### 1.2 The Interview Move

When faced with "design Amazon," your opening should be: "There are four distinct
sub-systems here — catalog, inventory, cart, and checkout — with very different
consistency and availability requirements. Given 45 minutes, I'd like to go deep on
inventory and checkout since those are the hardest, cover catalog architecture at
a higher level, and then handle flash sales as a special case. Does that scope work?"
This immediately signals senior-level thinking and prevents you from spending 30
minutes drawing a product page and never getting to the interesting parts.

### 1.3 Scale Numbers (Memorize These)

| Metric | Value | Why It Matters |
|--------|-------|----------------|
| Amazon products | 350M+ listings | Drives catalog sharding |
| Amazon peak sales | 3M items/minute (Prime Day) | Sets write throughput |
| Shopify Black Friday 2021 | 75M requests in 30 min | 2.5M req/sec burst |
| Flash sale peak | 100K inventory ops/sec | Sets Redis tier sizing |
| Average order value | ~$50 (varies) | Sets payment processing volume |
| Cart items per user | 3–8 typical | Sets cart data size |
| Checkout p99 latency target | < 2 seconds | Sets timeout budgets |
| Product image size | 200 KB–2 MB | Sets CDN bandwidth |
| Orders per day (Amazon) | ~12M | Sets DB write throughput |
| Inventory hold TTL | 15 minutes | Sets reservation expiry |

---

## Part 2: Product Catalog Architecture

### 2.1 Catalog Scale and Sharding Strategy

The product catalog at Amazon scale contains over 350 million product listings. Each
listing has structured metadata (title, price, brand, dimensions, weight), semi-structured
attributes (varies by category — a laptop has RAM and screen size; a shirt has size
and color), rich media (5–20 product images), user-generated content (reviews, Q&A),
and seller information (multiple sellers may offer the same product at different prices).
Total catalog storage at this scale exceeds 1 petabyte when images are included.

The metadata layer — title, price, attributes, seller info — averages about 2 KB per
product. For 500 million products, that is roughly 1 TB of structured product metadata.
This fits comfortably in a distributed NoSQL store like DynamoDB or Cassandra, sharded
by product ID. The primary access pattern for catalog lookups is always by product ID
(fetching a specific product page), making product_id a natural and effective partition
key. Secondary access patterns — browsing a category, filtering by brand — are served
by Elasticsearch, not the primary store.

Product images require a separate storage tier. At 500 KB average per image and 10
images per product, 500 million products generate 2.5 petabytes of image data. These
are stored in object storage (S3 or equivalent), then distributed through a global CDN.
Image URLs are stored in the product metadata as plain strings. The CDN handles all
image serving, achieving 99%+ cache hit rates because product images rarely change and
are highly cacheable. CloudFront or Akamai can serve hundreds of thousands of image
requests per second from edge caches without touching the origin.

The catalog sharding strategy at Amazon uses consistent hashing by product ID across
hundreds of DynamoDB partitions. Each partition serves roughly 1–5 million products.
Hot products (best-sellers, viral items) receive additional caching at the application
layer via an in-process cache or a dedicated Redis tier for the top 100K products by
view count. This two-level caching — Redis for hot items, DynamoDB for the long tail —
means 80–90% of catalog reads never reach the primary database.

### 2.2 Product Variants and SKU Architecture

A crucial modeling decision is the relationship between products and SKUs. A "product"
is the conceptual item: "Nike Air Max 270 Running Shoe." A "SKU" (Stock Keeping Unit)
is a specific, purchasable variant: "Nike Air Max 270, Size 10, Color: Black/White,
SKU: NK-AM270-10-BW." One product maps to many SKUs. For clothing, a single product
might have 50+ SKUs (5 sizes × 5 colors × 2 widths). The catalog must model this
cleanly because inventory is tracked at the SKU level, not the product level.

The data model uses three distinct entities: the Product (display, description, shared
attributes), the SKU (variant-specific attributes and price), and the Inventory record
(per-SKU, per-warehouse stock count). This separation allows the product page to load
quickly (one DynamoDB read for the product entity) and then lazily load variant
availability (a separate read for all SKUs of that product). The product-to-SKU
mapping is stored as a denormalized list on the Product record to avoid a join for
the most common case (showing all variants on a product page).

### 2.3 Elasticsearch for Product Search

Product search is one of the hardest parts of the catalog system to get right.
Customers search using natural language ("blue running shoes size 10 under $100") and
expect results ranked by relevance plus filtering by facets (category, brand, price
range, rating, availability). A relational database cannot do this efficiently.
Elasticsearch is the standard choice because it combines full-text search (BM25
relevance ranking) with faceted aggregations in a single query.

The Elasticsearch index for products is a denormalized document that combines all the
data needed for search and display in one place: product title, description, brand,
category, price, average rating, review count, availability flag, and all variant
attributes. Denormalization is intentional — Elasticsearch is not a primary store;
it is a search index maintained in sync with the primary DynamoDB store. When a
product is updated, the primary store is updated first, then an event is published
to a Kafka topic, and a consumer asynchronously updates the Elasticsearch index.
This asynchronous sync means search results can be up to 30 seconds stale, which is
acceptable for catalog display.

BM25 ranking in Elasticsearch handles the base relevance scoring, but e-commerce
search requires custom ranking signals on top. Products are re-ranked after the
initial Elasticsearch score by blending in business signals: sales velocity (GMV in
the last 7 days), seller rating, price competitiveness (is this price at or below
market average?), and sponsored product bids. This re-ranking happens in a lightweight
service that takes Elasticsearch's top-100 results and applies a scoring function to
produce the final top-20 shown to the user.

Faceted search — "show me all red Nike shoes between $50 and $100 with 4+ stars" —
works via Elasticsearch's aggregations API. The query includes both filter clauses
(narrow the result set) and aggregation clauses (count documents per facet value for
the sidebar). A single Elasticsearch query can retrieve the filtered product list and
compute facet counts in one round trip, which is why Elasticsearch is preferred over
a relational database for this use case.

### 2.4 Content Delivery for Product Images

Product image serving is a solved problem at scale, but the implementation details
matter. Images are stored in S3 with a URL structure that encodes the product ID and
variant. Multiple resolutions are pre-generated at upload time: thumbnail (80×80),
medium (400×400), large (1200×1200), and original. This is done by a media processing
service that runs on Lambda or a dedicated image processor when a seller uploads a new
image. Pre-generating resolutions avoids on-the-fly resizing (which is expensive and
unpredictable in latency) and ensures each resolution has a stable, cacheable URL.

The CDN configuration for product images uses a very long TTL — 365 days — with
cache-busting via URL versioning. When an image changes (a seller updates their product
photo), the new image gets a new URL (with an updated version parameter or hash), and
the old URL naturally expires. This means the CDN cache is always fresh for the
current image URL, and there is no need to issue CDN cache invalidations for the
common case. Cache invalidation is one of the hardest problems in computer science
and one of the most expensive operations at CDN scale; URL versioning sidesteps it
entirely for images.

---

## Part 3: Inventory Management — The Core Consistency Problem

### 3.1 Why Inventory Is Hard

Inventory management seems simple on the surface: decrement a counter when someone
buys something. The difficulty emerges at scale when thousands of users are trying to
buy the last few items of a popular product simultaneously. This is a classic
concurrent-update problem on shared mutable state, and every naive approach either
oversells (bad) or creates unacceptable contention (slow).

The naive approach is a simple SQL UPDATE:

```sql
UPDATE inventory
SET quantity_available = quantity_available - 1
WHERE sku_id = 'NK-AM270-10-BW'
  AND quantity_available > 0;
```

This works correctly on a single database instance with row-level locking. The problem
is throughput: this statement acquires an exclusive lock on the inventory row for the
duration of the transaction. At 10,000 concurrent purchases of the same SKU per second,
each request is waiting for the previous one to release the lock. The serialization
bottleneck kills throughput. Single-row throughput with this approach maxes out at a
few thousand transactions per second — completely inadequate for flash sales or popular
products.

### 3.2 The Reservation Pattern

The reservation pattern is the correct solution for general inventory management. It
uses a two-phase approach that separates "I want to buy this" from "I have bought this."

**Phase 1 — Reserve:** When a user adds an item to their cart or begins checkout, the
system creates an inventory reservation: a record saying "1 unit of SKU X is reserved
for user Y until time T." The available count is decremented atomically, but the item
is not yet sold. The reservation has a TTL — typically 15 minutes — after which it
expires automatically if the purchase is not completed.

**Phase 2 — Confirm or Cancel:** When the user completes checkout and payment succeeds,
the reservation is converted to a confirmed purchase. The "reserved" count moves to
"sold." If payment fails, or if the reservation TTL expires, the reservation is
cancelled: the item is returned to the available pool, and another user can purchase it.

```
┌─────────────────────────────────────────────────────────────┐
│                  Inventory Reservation Flow                  │
│                                                             │
│  Available: 5    Reserved: 0    Sold: 0                     │
│       │                                                     │
│  User adds to cart                                          │
│       │                                                     │
│  Available: 4    Reserved: 1    Sold: 0   (TTL: 15 min)    │
│       │                                                     │
│  ┌────┴────────────────────────────────────┐               │
│  │ Payment SUCCESS          Payment FAIL   │               │
│  │      │                       │         │               │
│  │ Available: 4           Available: 5    │               │
│  │ Reserved: 0            Reserved: 0    │               │
│  │ Sold: 1                Sold: 0        │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

The reservation approach has a key advantage over the naive decrement: the TTL-based
automatic expiry means the system self-heals from abandoned checkouts without requiring
explicit cleanup. If a user starts checkout, their browser crashes, and they never
complete it, the reservation expires in 15 minutes and the item goes back on sale. This
is much cleaner than requiring explicit "release inventory" calls from a client that
may have already disappeared.

### 3.3 Optimistic vs. Pessimistic Locking

Within the reservation pattern, there are two locking strategies for the actual
inventory decrement operation: optimistic locking and pessimistic locking.

**Pessimistic locking** acquires an exclusive lock on the inventory row before reading
and decrementing. In SQL, this is `SELECT ... FOR UPDATE`. It guarantees correctness
but creates a serialization bottleneck: only one transaction can hold the lock at a
time. Under high concurrency for a popular item, all transactions queue up behind the
lock, and throughput is limited to the rate at which the database can process one
transaction at a time for that row.

**Optimistic locking** reads the current inventory count, performs the decrement in
memory, and then updates the row only if the count has not changed since the read.
This uses a version number or compare-and-swap (CAS):

```sql
UPDATE inventory
SET quantity_available = quantity_available - 1,
    version = version + 1
WHERE sku_id = 'NK-AM270-10-BW'
  AND quantity_available > 0
  AND version = :expected_version;
```

If this UPDATE affects 0 rows (because another transaction already changed the version),
the caller retries. Under low to medium concurrency, optimistic locking has higher
throughput than pessimistic locking because it does not hold locks. Under very high
concurrency (thousands of concurrent transactions for the same row), the retry rate
becomes so high that optimistic locking performs worse than pessimistic locking.

The right choice depends on the scenario. For general inventory management (not flash
sales), optimistic locking with retries works well. For flash sales, neither SQL-based
approach is sufficient — you need Redis atomic operations.

### 3.4 Multi-Warehouse Inventory

At Amazon scale, inventory is not stored in one location. A single SKU might have
inventory distributed across 50 fulfillment centers globally. The inventory service
must track stock at the SKU-warehouse level, not just the SKU level. This creates
additional complexity: when a user in New York orders a product, should it ship from
the New Jersey warehouse (close, 2 days delivery) or the Texas warehouse (farther,
5 days delivery)? The choice affects delivery time, cost, and customer satisfaction.

The multi-warehouse inventory model stores a separate record per SKU per warehouse.
The total available inventory for a SKU is the sum across all warehouses that can
serve the customer's delivery address within the expected delivery window. When
reserving inventory, the system selects the optimal warehouse using a scoring function
that considers proximity, shipping cost, and current stock level (to avoid draining
one warehouse while another has surplus).

For display purposes ("3 left in stock"), the count shown to the user is the total
across all warehouses that can deliver within the prime shipping window. This denormalized
"displayable inventory count" is computed periodically and cached, because computing
it in real time across 50 warehouses for each product page view would be prohibitively
expensive. The display count can be eventually consistent — if it is 30 seconds stale,
no harm done. The actual reservation must be strongly consistent.

### 3.5 Five-Level Progression: Inventory System

**Intern:** "Decrement the database counter when someone buys something."
Does not consider concurrent purchases, oversell, or failures.

**Junior Engineer:** "Use a database transaction with row-level locking to ensure
only one user gets the last item." Correct but does not scale — creates a
serialization bottleneck at high concurrency.

**Mid-level Engineer:** "Use optimistic locking with a version field. If the update
fails due to a concurrent modification, retry up to 3 times." Handles moderate
concurrency. Still limited for flash sale scenarios.

**Senior Engineer:** "Use the reservation pattern — two-phase reserve/confirm with a
TTL. Reserve on add-to-cart, confirm on payment success, auto-release on TTL expiry.
For the reservation increment itself, use SELECT FOR UPDATE with a short transaction.
This separates the checkout flow from the payment flow and gives the system a
15-minute window to recover from partial failures." Correct production approach.

**Staff Engineer:** "Layer the solution: Redis DECR for inventory counters (atomic,
10M ops/sec, no locking), backed by a SQL source of truth. Redis counter is seeded at
sale start. Each decrement below zero is rejected. Successfully decremented requests
enter a purchase queue; a consumer writes confirmed purchases to the SQL DB and
processes payment. For multi-warehouse, maintain per-warehouse counters in Redis and
route reservations to the warehouse with the best score (proximity × availability).
Add a compensation layer: if payment fails after a Redis decrement, increment the
counter back. If the Redis node fails, fall back to SQL with pessimistic locking at
reduced capacity." Full production answer with failure modes addressed.

### 3.6 Brainstorming Q&A

**Q: How do you handle inventory display when items are reserved but not yet
purchased? Do you show the user the pre-reservation or post-reservation count?**

A: This is a nuanced UX and consistency tradeoff. If you show the pre-reservation
count ("10 in stock") but 8 of those are already in other users' active carts and
will likely be purchased, you are misleading the user. If you show post-reservation
count ("2 available"), you might show 0 when 8 reservations are about to expire in 14
minutes. Most production systems show the post-reservation count, but add contextual
messaging: "Only 2 left — 8 in customers' carts right now" (Amazon does something
similar). The inventory display value is read from the Redis counter (which reflects
reservations) and cached at the product service level with a 10-second TTL. This
gives customers accurate information with a small lag — good enough for UX without
requiring a live inventory read on every product page view.

**Q: What happens if the reservation expires but the user is still in the middle of
entering payment information?**

A: The system should warn the user before the reservation expires. At T-5 minutes,
the checkout page displays a countdown: "Your item is reserved for 5 more minutes."
If the reservation expires while they are still on the page, the page should
automatically check whether the item is still available (via a JavaScript polling
call) and either re-reserve it (if stock remains) or show an "out of stock" message.
If the item is re-reserved, the TTL resets. If it is not, the user is told the item
sold out while they were checking out — this is a legitimate outcome and the user
experience should communicate it clearly and offer alternatives. The backend handles
this via a TTL-based expiry mechanism in Redis (using EXPIRE) that automatically
releases the counter when the reservation record expires, making the inventory
available to the next user without any explicit cleanup job.

---

## Part 4: Flash Sale Architecture

### 4.1 The Flash Sale Problem

A flash sale is an extreme stress test: a massive burst of demand for a severely
limited supply, starting at a precise instant. Amazon Prime Day and Shopify's
Black Friday are real-world examples. The system properties that work for normal
traffic are completely wrong for flash sales. Normal inventory management: lazy
evaluation, eventual consistency fine for display, moderate concurrency. Flash sale
inventory management: every millisecond of staleness can result in oversell, 10,000x
normal traffic, every optimization matters.

The failure modes are instructive. In 2018, Amazon Prime Day experienced a 90-minute
partial outage when a viral product page (dog food, ironically) generated catastrophic
traffic to services that had not been pre-warmed. The bottleneck was not the core
infrastructure but the data layer — caches had not been pre-populated, so every
request went to the database, which was provisioned for 100x less load. Pre-warming
caches is not optional for flash sales; it is table stakes.

### 4.2 Pre-Sale Preparation

Flash sale preparation begins hours before the sale opens. The sequence:

**T-24 hours:** Identify all products in the sale. Ensure their catalog data, images,
and pricing are fully cached at every CDN edge node globally. Run a "cache warming"
job that fetches every product page in the sale to populate edge caches. Verify
Elasticsearch indexes are current.

**T-4 hours:** Load inventory counts into Redis. Create a Redis key per SKU
(`inventory:sku:12345`) and set it to the initial stock count using SET. This Redis
key is the authoritative inventory counter for the duration of the flash sale.
Simultaneously, snapshot the current inventory count in SQL as the "pre-sale" value.

**T-1 hour:** Scale up all services. Flash sale traffic is predictable — you know
exactly when it starts. Use auto-scaling policies that target 3x normal capacity.
Pre-scale databases (increase read replicas, increase connection pool sizes). Enable
the virtual waiting room service.

**T-15 minutes:** Disable non-essential features to reduce system load. Cart
recommendations, "customers also viewed" sections, and A/B tests can be disabled
during the flash sale window. Every reduced feature is one less service that can fail
under load. This is the "circuit breaker" pattern applied proactively.

**T-0:** The sale opens. Traffic spikes immediately. The virtual waiting room begins
admitting users at a controlled rate.

### 4.3 Redis Atomic DECR for Inventory

The core insight of flash sale inventory management is this: Redis DECR is atomic
at the single-key level. No matter how many concurrent clients call DECR on the same
key, Redis serializes these operations and guarantees that each call either decrements
by exactly 1 or returns an error. Redis can handle over 10 million such operations
per second on a single node. This is the right tool for flash sale inventory.

The implementation:

```python
import redis

r = redis.Redis(host='inventory-redis', port=6379)

def try_reserve_flash_sale_item(sku_id: str) -> bool:
    """
    Attempt to reserve one unit of a flash sale item.
    Returns True if reservation succeeded, False if sold out.
    """
    key = f"inventory:flash:{sku_id}"
    
    # DECR is atomic - no race condition possible
    remaining = r.decr(key)
    
    if remaining < 0:
        # We went below zero - put the unit back (compensate)
        r.incr(key)
        return False
    
    return True
```

The problem with the simple DECR approach is the check-then-act race condition
in the code above: if the count is 0 and 100 concurrent threads call DECR, all 100
will get back a negative number, and all 100 will call INCR to compensate — but
between DECR and INCR, the counter is temporarily -100. More critically, if the
service crashes between DECR and INCR, the inventory is permanently decremented
without a corresponding sale, creating a phantom reservation.

The correct approach uses a Lua script to make the check-and-decrement atomic:

```lua
-- lua/atomic_decrement.lua
-- KEYS[1] = inventory key (e.g., "inventory:flash:12345")
-- Returns 1 if reservation succeeded, 0 if sold out

local current = redis.call('GET', KEYS[1])
if current == false then
    return 0  -- key does not exist, sold out
end

local count = tonumber(current)
if count <= 0 then
    return 0  -- sold out
end

redis.call('DECR', KEYS[1])
return 1
```

```python
# Load and execute the Lua script
with open('lua/atomic_decrement.lua', 'r') as f:
    lua_script = f.read()

atomic_decr = r.register_script(lua_script)

def try_reserve_flash_sale_item(sku_id: str) -> bool:
    key = f"inventory:flash:{sku_id}"
    result = atomic_decr(keys=[key])
    return result == 1
```

Lua scripts in Redis execute atomically — no other Redis command can run between
the GET and the DECR in the script. This eliminates the race condition entirely. The
script is also idempotent from the caller's perspective: it either reserves 1 unit
and returns 1, or it sees 0 inventory and returns 0. There is no intermediate state.

### 4.4 Virtual Waiting Room

At 10 million concurrent users hitting the sale page simultaneously, even a Redis-
backed system will be overwhelmed if every user instantly proceeds to checkout.
The virtual waiting room is the mechanism that throttles user admission to the checkout
flow at a rate the downstream system can handle.

The virtual waiting room works as follows: when the sale opens, all new users who
request access are given a queue position instead of direct access. The position is
stored in Redis as a sorted set (`ZADD queue:{sale_id} {timestamp} {user_id}`). A
background process admits users from the queue at a controlled rate — say, 5,000
users per second into the checkout flow. Users who have been admitted receive a
short-lived access token (JWT, 10-minute TTL) that allows them to proceed to the
product page and checkout. Users still in the queue see their estimated wait time
and a progress indicator.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Virtual Waiting Room Flow                    │
│                                                                 │
│  10M users     ──┐                                             │
│  request         │     ┌──────────────────┐                    │
│  access          └────►│  Queue Service   │                    │
│                         │  (Redis Sorted   │                    │
│                         │   Set, 10M keys) │                    │
│                         └────────┬─────────┘                    │
│                                  │ Admit 5,000/sec              │
│                                  ▼                              │
│                         ┌──────────────────┐                    │
│                         │  Access Token    │                    │
│                         │  Generator       │                    │
│                         │  (JWT, 10 min)   │                    │
│                         └────────┬─────────┘                    │
│                                  │                              │
│                                  ▼                              │
│                         ┌──────────────────┐                    │
│                         │  Checkout Flow   │                    │
│                         │  (5K users/sec   │                    │
│                         │   sustainable)   │                    │
│                         └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

The admission rate (5,000 users/sec in this example) is set based on the capacity
of the checkout system and the inventory drain rate. If there are 100,000 units
available and you want the sale to last 20 minutes (for excitement and marketing
reasons), the drain rate should be approximately 100,000 / (20 × 60) ≈ 83 units/sec.
But since not every admitted user will complete a purchase, the admission rate
is set higher — perhaps 5–10x the purchase rate — with the expectation that only
10–20% of admitted users actually complete a purchase in the session.

### 4.5 Queue-Based Purchase Flow

For the hottest items (limited-edition sneakers, concert tickets, gaming consoles
at launch), even the virtual waiting room is not enough. The queue-based purchase
flow adds an additional layer: instead of users calling the checkout API directly,
they submit a purchase request to a queue, and the queue consumer processes requests
sequentially at a sustainable rate.

```
User submits "Buy Now" 
        │
        ▼
┌───────────────────┐      ┌─────────────┐
│  Purchase Queue   │      │  Queue      │
│  (Kafka/SQS)      │─────►│  Consumer   │
│  (millions of     │      │  (processes │
│   messages)       │      │  1K/sec)    │
└───────────────────┘      └──────┬──────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              Check Redis    Charge Payment  Create Order
              Inventory       (Stripe/etc)    Record
              Counter
                    │
              (Success/Fail)
                    │
                    ▼
             Notify User via
             WebSocket/SSE
```

The user does not wait synchronously for the checkout to complete. They receive
an immediate "request received" response with a job ID, and the frontend polls
(or maintains a WebSocket connection) to receive the result when the queue
consumer processes their request. This decoupling absorbs the traffic spike
at the entry point and processes purchases at a metered, sustainable rate.

### 4.6 Brainstorming Q&A

**Q: What happens if the Redis instance holding flash sale inventory counters fails
mid-sale?**

A: This is the single hardest operational question for flash sale systems. The first
line of defense is Redis Sentinel or Redis Cluster with automatic failover: if the
primary fails, a replica is promoted within seconds. The inventory counter is replicated
synchronously (WAIT command) or with minimal lag to at least one replica, so failover
loses at most a few operations. If the failover takes 10 seconds, you pause the sale
for 10 seconds — a minor but acceptable interruption.

If Redis fails completely (unlikely with a properly configured cluster), the system
falls back to the SQL database with pessimistic locking. This fallback runs at perhaps
1/100th the throughput of Redis, so the system continues operating but at reduced
capacity. The virtual waiting room's admission rate is reduced proportionally to
prevent overwhelming the SQL fallback. The important thing is to have this fallback
path tested and ready — not as a theoretical exercise but as a runbook that gets
tested in staging before every major sale. The fallback mode should be triggered via
a feature flag, not an automatic circuit breaker, because the operator needs to
understand why Redis is unavailable before switching modes.

**Q: How do you prevent the "thundering herd" when a flash sale opens at exactly
T=0?**

A: The thundering herd is when millions of users, all waiting for the same moment,
send requests simultaneously the instant the clock ticks over. Several mitigations
work in combination. First, the virtual waiting room begins slightly before T=0 — at
T-30 seconds — to start building the queue before the rush. Second, the CDN layer
can return a cached "sale not started yet" page until T=0, which reduces the number
of requests that reach origin servers to only the users who refresh at exactly the
right moment. Third, the actual T=0 trigger can be randomized slightly (±500ms)
so that the spike is spread over 1 second instead of all hitting at once. Fourth,
the access token mechanism means that even users who get to the queue immediately
cannot overwhelm the checkout system because their token must pass through the
admission gate before checkout is accessible. Each of these mitigations reduces the
peak by a small factor; combined, they can reduce the thundering herd from 10 million
concurrent requests to perhaps 500,000 — a 20x reduction that makes the system
tractable.

---

## Part 5: Shopping Cart Architecture

### 5.1 Cart Storage: Session-Based vs. Persistent

The shopping cart is one of the most discussed design decisions in e-commerce systems
because it sits at the intersection of UX, performance, and consistency. There are
two primary approaches: client-side storage (the cart lives in the browser's
localStorage or a cookie) and server-side storage (the cart lives in a database).

Client-side carts are simple to implement, require no server infrastructure, and
are highly available by definition (they never make a network call to load). The
fatal flaws: they are device-specific (a cart built on your phone is invisible on
your laptop), they are lost when the browser data is cleared, they cannot enforce
real-time price or inventory validation, and they cannot be used for cart abandonment
re-engagement emails ("You left something in your cart!"). For any serious e-commerce
platform, client-side carts are a non-starter.

Server-side carts use the server as the source of truth. Redis is the correct choice
for the hot-path storage because cart reads and writes are extremely frequent (every
page load refreshes the cart icon count), the data structure is naturally key-value
(user ID → cart contents), and Redis supports TTL-based expiry for abandoned carts
automatically. A secondary, durable store (PostgreSQL) is used for long-term cart
persistence and cart abandonment analytics. Cart data is written to Redis immediately
and asynchronously replicated to PostgreSQL.

### 5.2 Cart Data Model

```
Cart (Redis Hash)
  Key: cart:{user_id}
  Fields:
    - items: JSON list of {sku_id, quantity, added_at, price_snapshot}
    - updated_at: timestamp
    - currency: "USD"
    - applied_coupon: coupon_code or null

TTL: 30 days (reset on every access)
```

The `price_snapshot` field stores the price at the time the item was added to the
cart. This enables two behaviors: showing the user whether the price has changed
since they added the item ("Price dropped by $5!") and enforcing price-at-checkout
semantics. Amazon uses price-at-checkout: the actual charge is the current price
at the moment of purchase, not the price when the item was added. Some retailers
use price-at-add for a better UX: the customer locks in today's price by adding
to cart. The data model supports both by storing the snapshot and comparing it to
the current price at checkout time.

### 5.3 Anonymous Cart to Authenticated Cart Merging

One of the trickiest edge cases in cart design is the anonymous-to-authenticated
transition. A user browses the site, adds 3 items to their cart as a guest, then
logs in. Their account already has 2 items in the cart from a previous session.
What does the cart look like after login?

There are three merge strategies:

**Overwrite:** The authenticated cart replaces the anonymous cart. Simple to implement,
terrible UX — the user loses the 3 items they just added.

**Append:** The anonymous cart items are added to the authenticated cart. Better, but
creates duplicates if the same SKU is in both carts. Resolution: for duplicate SKUs,
take the higher quantity (not sum — you probably don't want to 2x every item already
in the cart).

**Interleave with user choice:** Present the user with both carts and let them choose
what to keep. Best UX for high-value items; too much friction for commodity shopping.

Most production systems (including Amazon) use the append-with-deduplication strategy.
The implementation runs at login time: fetch both carts, merge them with deduplication
logic, write the merged result to the authenticated user's cart key, and expire the
anonymous cart key. This is a short transaction — read both keys, compute merge,
write result — and is executed atomically using a Redis transaction (MULTI/EXEC) to
prevent partial merges if the service crashes mid-operation.

### 5.4 Cart Abandonment Recovery

Cart abandonment is a major revenue recovery mechanism. About 70% of all shopping
carts are abandoned before checkout. A well-designed re-engagement system can recover
5–15% of abandoned revenue through targeted emails and push notifications.

The technical architecture: when a cart is updated (item added or quantity changed),
the cart service publishes an event to a Kafka topic. A cart abandonment service
consumes this topic and schedules a re-engagement job: "if this cart has not been
checked out within 24 hours, send an email." The job is implemented as a delayed task
in a job queue (Celery + Redis or AWS SQS with delay). If the user checks out within
24 hours, a "cancel" event is published and the re-engagement job is removed.

The email content requires knowing what is in the cart at the time of sending, which
requires reading the cart from Redis (still valid after 30 days TTL) or from the
PostgreSQL replica. The email personalizes based on the specific items abandoned and
may include dynamic pricing (if items are on sale, show the new lower price) or
urgency signals ("Only 2 left in stock!").

---

## Part 6: Checkout as a Saga

### 6.1 The Checkout Problem

Checkout is the transaction that converts a cart into an order and processes payment.
It appears simple: charge the card, ship the stuff. The hidden complexity: checkout
spans multiple independent services (inventory, payment processor, order database,
notification service, fulfillment) and each step can fail. A distributed transaction
across these services is not possible — payment processors are external systems that
do not participate in a distributed transaction coordinator. The Saga pattern is the
correct solution.

### 6.2 The Saga Pattern

A Saga is a sequence of local transactions, each of which publishes an event or
message to trigger the next transaction. If any step fails, the Saga executes
compensating transactions to undo the work done by the preceding steps.

The checkout Saga has the following steps:

```
Step 1: Validate Cart
  Action: Read cart, verify all items exist and prices are current
  Compensating: (none — read-only step)

Step 2: Reserve Inventory
  Action: Decrement available inventory for all SKUs in cart
  Compensating: Increment inventory back (release reservation)

Step 3: Create Pending Order
  Action: Create order record in DB with status=PENDING
  Compensating: Mark order as CANCELLED

Step 4: Process Payment
  Action: Charge customer's payment method via payment gateway
  Compensating: Issue refund via payment gateway

Step 5: Confirm Inventory
  Action: Convert inventory reservation to confirmed purchase
  Compensating: Release inventory reservation

Step 6: Update Order Status
  Action: Set order status to CONFIRMED
  Compensating: (handled by Step 4's compensating transaction)

Step 7: Trigger Fulfillment
  Action: Send order to fulfillment service
  Compensating: Cancel fulfillment request (if not yet shipped)

Step 8: Send Confirmation
  Action: Send order confirmation email/notification
  Compensating: (none — notification already sent)
```

If Step 4 (payment) fails, the Saga executes: compensate Step 3 (cancel order),
compensate Step 2 (release inventory), and the checkout fails gracefully. The user
sees "Payment failed, please try another payment method" and their cart is restored.
If Step 7 (fulfillment) fails after payment has been processed, the Saga refunds
the payment (Step 4 compensation) and cancels the order (Step 3 compensation).

### 6.3 Idempotency Keys

The biggest risk in checkout is double-charging: a customer submits their payment,
the network times out, they retry, and are charged twice. Idempotency keys prevent
this. The checkout service generates a unique idempotency key at the start of each
checkout session (a UUID tied to the cart ID and timestamp). This key is included
in every call to the payment gateway. If the payment gateway receives two requests
with the same idempotency key, it processes the payment once and returns the same
response to both requests. The customer is charged exactly once regardless of how
many retries occur.

Idempotency must also be enforced at the inventory layer. If the "reserve inventory"
step is retried, it should not decrement the counter twice. The implementation uses
a reservation ID: the first call with reservation_id=R1 decrements the counter and
records that R1 is associated with SKU X. A second call with the same reservation_id
R1 is a no-op (the reservation already exists). This requires checking for the
reservation record before decrementing, which must be done atomically (check-and-set).

```python
def reserve_inventory_idempotent(sku_id: str, quantity: int,
                                  reservation_id: str) -> bool:
    """
    Idempotent inventory reservation.
    Returns True if reservation succeeded or already exists.
    Returns False if insufficient inventory.
    """
    reservation_key = f"reservation:{reservation_id}"
    inventory_key = f"inventory:{sku_id}"
    
    # Check if reservation already exists (idempotency)
    existing = r.get(reservation_key)
    if existing:
        return existing == b"1"  # Return previous result
    
    # Attempt reservation via Lua script (atomic check-and-decrement)
    success = atomic_reserve(keys=[inventory_key, reservation_key],
                             args=[quantity, 900])  # 900s = 15min TTL
    
    # Cache result for idempotency (with same TTL)
    r.set(reservation_key, "1" if success else "0", ex=900)
    return bool(success)
```

### 6.4 Checkout State Machine

```
                        ┌─────────┐
                        │  CART   │
                        └────┬────┘
                             │ User clicks "Checkout"
                             ▼
                        ┌─────────┐
                        │VALIDATING│
                        └────┬────┘
                             │ Cart valid, inventory available
                             ▼
                   ┌──────────────────┐
                   │INVENTORY_RESERVED│
                   └────────┬─────────┘
                            │ Proceed to payment
                            ▼
                   ┌──────────────────┐
                   │ PAYMENT_PENDING  │
                   └────────┬─────────┘
                    ┌───────┴────────┐
              Payment OK        Payment FAIL
                    │                │
                    ▼                ▼
           ┌─────────────┐   ┌──────────────┐
           │  CONFIRMED  │   │ PAYMENT_FAILED│
           └──────┬──────┘   └──────┬───────┘
                  │                 │ Release inventory
                  │                 ▼
                  │          ┌──────────────┐
                  │          │   CANCELLED  │
                  │          └──────────────┘
                  │ Fulfillment assigned
                  ▼
           ┌─────────────┐
           │  PROCESSING │
           └──────┬──────┘
                  │ Package shipped
                  ▼
           ┌─────────────┐
           │   SHIPPED   │
           └──────┬──────┘
                  │ Delivery confirmed
                  ▼
           ┌─────────────┐
           │  DELIVERED  │
           └──────┬──────┘
                  │ Return requested
                  ▼
           ┌─────────────┐
           │   RETURNED  │
           └─────────────┘
```

### 6.5 The Outbox Pattern for Reliable Event Publishing

A subtle failure mode in the checkout Saga: the order is created in the database,
but the event publishing to Kafka fails (network hiccup, Kafka is temporarily
unavailable). The order exists but the fulfillment service never receives it. The
Outbox pattern solves this.

Instead of publishing directly to Kafka during the transaction, the service writes
the event to an "outbox" table in the same database, within the same transaction as
the order creation. A separate "relay" service reads from the outbox table and
publishes to Kafka, deleting the outbox row upon successful publication. If Kafka
is unavailable, the relay retries. If the relay crashes, it restarts and replays
the unpublished outbox rows. The event is eventually published exactly once.

```sql
-- Outbox table
CREATE TABLE outbox_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    event_type  VARCHAR(100) NOT NULL,
    payload     JSONB NOT NULL,
    published   BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMP
);

-- Within the order creation transaction:
BEGIN;
INSERT INTO orders (id, user_id, status, ...) VALUES (...);
INSERT INTO outbox_events (event_type, payload) 
  VALUES ('ORDER_CREATED', '{"order_id": "...", "user_id": "..."}');
COMMIT;
-- The relay service will publish to Kafka asynchronously
```

### 6.6 Five-Level Progression: Checkout

**Intern:** "Put the checkout logic in one big function: validate cart, charge card,
reduce inventory, send email." Does not handle failures between steps.

**Junior Engineer:** "Use database transactions to make the checkout atomic." Misses
that the payment gateway is external and cannot participate in a DB transaction.

**Mid-level Engineer:** "Use a try/catch with explicit rollback steps: if payment
fails, release inventory; if inventory confirm fails, refund." Correct intent but
fragile — does not survive service restarts mid-checkout.

**Senior Engineer:** "Use the Saga pattern with a persistent saga state machine stored
in the database. Each step updates the saga state. On service restart, incomplete
sagas are detected and resumed or rolled back. Add idempotency keys to prevent
double-charging on retry." Production-quality answer.

**Staff Engineer:** "Orchestration vs. choreography tradeoff: orchestrated Saga (one
Saga orchestrator service drives the sequence, with explicit state in the DB) gives
clearer failure visibility but is a single point of coordination; choreographed Saga
(each service emits events that trigger the next) is more decoupled but harder to debug.
At checkout scale, use orchestrated Saga with the orchestrator state in a dedicated
'saga_state' table. Add circuit breakers on the payment gateway call (external SLA
differs from internal). Use the Outbox pattern for all event publishing. Implement
idempotency at every layer. Add distributed tracing (trace_id in all events) so
you can reconstruct the full saga execution for debugging. Maintain a saga replay
mechanism for catastrophic failures." Complete Staff-level answer.

### 6.7 Brainstorming Q&A

**Q: What is the risk of the "confirm inventory" step failing after payment has
already succeeded?**

A: This is the most dangerous failure scenario in checkout because it means the
customer was charged but the inventory was not confirmed — the order might not be
fulfillable. The compensating transaction must refund the payment. However, payment
refunds have their own latency (seconds to minutes with external providers) and can
fail. The correct approach: do not fail silently. If the inventory confirm fails after
payment succeeds, the system must mark the saga as "requires manual intervention,"
alert the operations team, and proactively communicate with the customer (automated
email: "We're having trouble processing your order, you will receive a full refund
within 24 hours"). This is a runbook, not a purely automated flow. Additionally, the
frequency of this failure should be tracked as a key metric — if it is above 0.01%
of orders, there is a systemic problem to investigate. Prevention is better than
cure: the inventory reservation in Step 2 means inventory confirm in Step 5 should
almost never fail unless the warehouse reports that the reserved item is damaged or
lost, which is an operational exception.

**Q: How do you handle partial fulfillment? A customer ordered 5 items but only 4
are in stock at checkout time.**

A: This should not happen if inventory reservations are correct — checkout only
proceeds if all items can be reserved. But if it does happen (race condition, data
inconsistency), there are two options: fail the entire checkout (atomic, simpler, but
worse UX for the customer who wanted 4 of 5 items) or partial fulfill with
notification (ship the 4 available items, cancel and refund the 1 unavailable item,
email the customer explaining the situation). Amazon defaults to partial fulfillment
with notification for most cases. The system must split the order into a "fulfillable"
portion and a "cancelled with refund" portion, process them with separate saga
instances, and present a unified view in the customer's order history. Partial orders
also create partial fulfillment records at the warehouse level, which is a meaningful
increase in operational complexity. The simpler path — fail the whole checkout if any
item cannot be reserved — is defensible in a design interview and should be offered as
the starting point with partial fulfillment as the evolution for better UX.

---

## Part 7: Order Management System

### 7.1 Order State Machine and Event Sourcing

The order management system (OMS) tracks every order from creation through delivery
or return. It is a state machine as described in Section 6.4, but at scale, it is
also one of the highest-value data assets in the business: every order represents
revenue, and the history of what was ordered, when, and by whom drives inventory
forecasting, personalization, fraud detection, and financial reporting.

Event sourcing is an excellent fit for the OMS. Instead of storing only the current
state of an order, the system stores the complete history of every event that affected
the order: OrderCreated, PaymentProcessed, InventoryConfirmed, FulfillmentAssigned,
LabelPrinted, PackageShipped, DeliveryConfirmed, ReturnRequested, RefundIssued. The
current state of an order is derived by replaying these events. The event log is
immutable and append-only — events are never deleted or modified, only new events
are added. This makes the OMS a perfect audit trail and enables temporal queries
("what was the state of this order at 3 PM yesterday?").

```sql
CREATE TABLE order_events (
    id              BIGSERIAL PRIMARY KEY,
    order_id        UUID NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    event_data      JSONB NOT NULL,
    occurred_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    actor_id        VARCHAR(100),  -- user or system that triggered event
    INDEX idx_order_events_order_id (order_id, occurred_at)
);
```

For read performance, a materialized view of the current order state is maintained
in a separate table, updated by event handlers as events are applied. This gives the
read path O(1) access to the current order state without replaying the full event
history on every read.

### 7.2 Returns and Refunds: The Reverse Saga

Returns are a reverse saga: restock inventory and refund payment. The reverse saga
has the same idempotency and failure-mode requirements as the forward checkout saga,
with the additional complexity that returns may be partial (return 2 of 3 items in
an order) and may involve physical logistics (the customer ships the item back; only
restock inventory after the physical return is received and inspected).

The return state machine: ReturnRequested → ReturnLabelGenerated → ItemInTransit →
ItemReceived → ItemInspected → (ItemApproved → Refunded) or (ItemRejected →
CustomerNotified). Each state transition is an event in the event log.

### 7.3 Brainstorming Q&A

**Q: How do you handle the case where a customer disputes a charge after delivery?**

A: Charge disputes (chargebacks) initiated by customers through their bank bypass
the system's refund flow entirely. The bank reverses the charge and notifies the
merchant. The OMS must listen for chargeback webhooks from the payment gateway and
create a "ChargebackReceived" event. The operations team reviews the chargeback:
if it is fraudulent (the customer received the item but claimed otherwise), the
merchant can contest it with delivery evidence. If it is legitimate (item not received
despite shipping records showing delivery), the merchant accepts the chargeback. The
inventory is not restocked for chargebacks — the item has been physically delivered
or is otherwise unrecoverable. Chargeback rate is a key fraud signal: a high chargeback
rate on a specific seller or product category triggers fraud review. Integration with
the Fraud Detection system (Chapter 105) is critical here.

---

## Part 8: Pricing Engine

### 8.1 Price Complexity at Amazon Scale

Pricing at Amazon scale is not "a price field in the product table." Amazon has over
100 million products with prices that change multiple times per day based on competitive
intelligence, demand, inventory levels, seller competition, and algorithmic repricing.
The pricing engine must evaluate pricing rules at read time, not store a single static
price, and must apply the correct price to the correct customer at the correct time.

### 8.2 Price Tiers and Dynamic Pricing

Price tiers represent different prices for different customer segments: Prime members
get a different price than non-Prime members; business buyers get volume discounts;
employees get a corporate discount. The pricing engine applies tiers in priority order
and returns the lowest applicable price for the customer's segment.

Dynamic pricing adjusts prices algorithmically based on supply and demand signals.
Amazon's pricing engine reportedly updates prices 2.5 million times per day — about
1 price update per product per day on average, but with heavy concentration on popular
products. The price calculation logic:

```
base_price 
  × margin_adjustment(cost, target_margin)
  × competitive_factor(competitor_prices)
  × demand_factor(view_to_purchase_rate, inventory_days_remaining)
  × promotional_adjustment(active_promotions)
  = final_price
```

The "competitive factor" requires continuously scraping competitor prices (or buying
a competitive intelligence feed) and adjusting in response. This is a separate data
pipeline problem.

### 8.3 Flash Sale Pricing

Flash sale prices are simple in concept — a percentage off the base price for a
limited time window — but require careful implementation. The price must be atomically
locked during the sale window: a race condition where the base price changes during
a flash sale (triggering a reprice) must not corrupt the flash sale price. The
implementation stores flash sale prices separately from base prices, with explicit
start and end timestamps, and the pricing engine always checks for an active flash
sale price before falling back to the base price.

```sql
CREATE TABLE product_prices (
    sku_id          VARCHAR(100) NOT NULL,
    price_type      VARCHAR(50) NOT NULL,  -- 'base', 'prime', 'flash', 'employee'
    amount          DECIMAL(10, 2) NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    valid_from      TIMESTAMP NOT NULL,
    valid_until     TIMESTAMP,  -- NULL = no expiry
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sku_id, price_type, valid_from)
);

-- Current price query
SELECT amount FROM product_prices
WHERE sku_id = :sku_id
  AND price_type IN ('flash', 'prime', 'base')
  AND valid_from <= NOW()
  AND (valid_until IS NULL OR valid_until > NOW())
ORDER BY 
  CASE price_type 
    WHEN 'flash' THEN 1 
    WHEN 'prime' THEN 2 
    WHEN 'base' THEN 3 
  END
LIMIT 1;
```

### 8.4 A/B Price Testing

Running price experiments is critical for optimizing revenue but requires careful
implementation to avoid customer-perceived unfairness. A/B price testing should
show different prices to different user segments (not different prices to the same
user across sessions, which is obviously unfair and legally problematic in some
jurisdictions). Users are assigned to price test groups based on their user ID hash,
which is stable across sessions. The experiment is recorded in an experiment assignment
table, and the checkout price is looked up from the experiment assignment. The
experiment framework ensures that a user in group A always sees the group A price
across all sessions, devices, and page loads.

---

## Part 9: Search Architecture

### 9.1 Elasticsearch Index Design for Products

The Elasticsearch product index is one of the largest and most query-intensive
Elasticsearch deployments in any company. At Amazon scale (350M+ products), a single
Elasticsearch index cannot practically fit on one cluster — the index is sharded
across clusters, often by product category (separate clusters for Electronics, Apparel,
Books, etc.) or by some hash of product ID.

The mapping for a product document in Elasticsearch:

```json
{
  "product_id": "B08N5WRWNW",
  "title": "Echo Dot (4th Gen) Smart Speaker with Alexa",
  "description": "Meet the all-new Echo Dot...",
  "brand": "Amazon",
  "category_path": ["Electronics", "Smart Home", "Smart Speakers"],
  "price": 49.99,
  "prime_price": 44.99,
  "average_rating": 4.7,
  "review_count": 152847,
  "availability": "in_stock",
  "prime_eligible": true,
  "tags": ["alexa", "smart speaker", "wifi", "voice assistant"],
  "attributes": {
    "connectivity": "WiFi, Bluetooth",
    "color": "Charcoal",
    "compatible_devices": ["Alexa", "Echo Hub"]
  },
  "popularity_score": 98.7,
  "updated_at": "2024-01-15T10:30:00Z"
}
```

Nested fields (attributes, tags) enable faceted filtering. The `category_path` array
enables hierarchical category browsing. `popularity_score` is a denormalized signal
computed offline (combining sales velocity, review count, and click-through rate)
that is used to boost popular items in search results.

### 9.2 Query Architecture

A product search query combines text matching with facet filtering and custom ranking:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless headphones",
            "fields": ["title^3", "brand^2", "description", "tags"],
            "type": "best_fields"
          }
        }
      ],
      "filter": [
        {"term": {"availability": "in_stock"}},
        {"range": {"price": {"gte": 50, "lte": 200}}},
        {"term": {"average_rating": {"gte": 4}}},
        {"term": {"prime_eligible": true}}
      ]
    }
  },
  "sort": [
    {"_score": {"order": "desc"}},
    {"popularity_score": {"order": "desc"}}
  ],
  "aggs": {
    "brands": {"terms": {"field": "brand", "size": 20}},
    "price_ranges": {
      "range": {
        "field": "price",
        "ranges": [
          {"to": 50},
          {"from": 50, "to": 100},
          {"from": 100, "to": 200},
          {"from": 200}
        ]
      }
    },
    "avg_rating_buckets": {
      "histogram": {"field": "average_rating", "interval": 1}
    }
  },
  "size": 20,
  "from": 0
}
```

The `aggs` section computes facet counts in the same query as the search results,
returning both in a single round trip. The facet counts show how many products match
each filter option, enabling the "Brands (Amazon: 1,234, Sony: 892, Bose: 456)"
sidebar. This is the defining feature of Elasticsearch-powered product search that
is practically impossible to replicate with SQL at this scale.

### 9.3 Search Ranking and Personalization

The initial Elasticsearch result is ranked by BM25 text relevance blended with
`popularity_score`. But e-commerce search benefits significantly from personalization:
a user who has previously purchased running shoes multiple times should see running
shoes ranked higher than dress shoes for the query "Nike shoes."

The personalized re-ranking pipeline:

1. Elasticsearch returns top 100 results ranked by BM25 + popularity.
2. A lightweight re-ranking service fetches the user's purchase history, browsing
   history, and category affinities.
3. Each of the 100 results is re-scored: `final_score = alpha × es_score + beta ×
   personalization_score + gamma × sponsored_bid`.
4. The top 20 re-ranked results are returned to the client.

The re-ranking step adds approximately 20–50 ms of latency, acceptable given that
the full search response must complete in under 200 ms to avoid user-perceived lag.

---

## Part 10: Recommendations Engine (Brief)

### 10.1 "Frequently Bought Together"

The "Frequently Bought Together" feature (users who bought product A also bought
products B and C) is powered by item-item collaborative filtering on the order history.
The offline computation: for every pair of products (A, B), count how many distinct
orders contained both A and B. Pairs with high co-occurrence count are stored in a
lookup table indexed by product ID. At query time, looking up the co-purchase
recommendations for product A is a simple key-value lookup: O(1), served from a cache.

The co-occurrence computation runs as a batch MapReduce or Spark job daily on the
order history. With 12 million orders per day and an average of 3 items per order,
there are approximately 36 million item pairs to aggregate daily. This is well within
Spark's processing capacity on a modest cluster.

### 10.2 "Customers Also Viewed"

"Customers Also Viewed" uses session-level co-view data: products viewed in the same
browsing session are associated. The implementation is an online computation: a
Kafka stream of product view events is processed in real time using a session window,
and co-view pairs are updated in a Redis sorted set (ZINCRBY to increment co-view
count). The top N co-viewed products for any given product are returned via a Redis
ZREVRANGE query. This real-time approach allows new products (which have no order
history) to accumulate co-view signals immediately upon launch.

---

## Part 11: Multi-Warehouse Fulfillment

### 11.1 Warehouse Selection Algorithm

When an order is placed, the fulfillment routing service must decide which warehouse
ships the item. The decision affects delivery time, shipping cost, and customer
satisfaction. The warehouse selection algorithm scores each warehouse that has the
item in stock:

```
score = (distance_factor × w1) + (stock_level_factor × w2) + (shipping_cost_factor × w3)

distance_factor = 1 / (delivery_days + 1)   # Closer = higher score
stock_level_factor = min(stock / demand_forecast, 1)  # Avoid draining low stock
shipping_cost_factor = 1 / normalized_shipping_cost
```

The weights (w1, w2, w3) are tuned based on business priorities. If the company is
in cost-reduction mode, w3 (shipping cost) gets a higher weight. If the company is
competing on delivery speed (Amazon Prime same-day), w1 (distance) gets the highest
weight.

### 11.2 Split Shipments

When items in an order are in different warehouses and no single warehouse has all
items in stock, the fulfillment system must decide between: waiting for one warehouse
to restock all items (slow, customer dissatisfied), routing different items to
different warehouses and shipping them separately (faster for the customer, more
expensive due to multiple shipments), or canceling unavailable items and shipping
the rest.

Amazon defaults to split shipments for Prime orders: each item ships from the
optimal warehouse, potentially arriving at different times. The customer sees a
multi-package order in their order history. The OMS tracks each sub-shipment
separately with its own tracking number, and the order is considered "fully delivered"
only when all packages arrive. The customer is notified of each package separately.

---

## Part 12: Database Schemas

### 12.1 Product Catalog Schema

```sql
-- Product master record
CREATE TABLE products (
    product_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    description     TEXT,
    brand           VARCHAR(200),
    category_id     INT NOT NULL REFERENCES categories(id),
    seller_id       UUID REFERENCES sellers(id),
    status          VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_seller ON products(seller_id);
CREATE INDEX idx_products_status ON products(status, updated_at);

-- SKU (variant) table
CREATE TABLE skus (
    sku_id          VARCHAR(100) PRIMARY KEY,
    product_id      UUID NOT NULL REFERENCES products(product_id),
    attributes      JSONB NOT NULL DEFAULT '{}',  -- {"size":"L","color":"red"}
    weight_grams    INT,
    dimensions_cm   JSONB,  -- {"length":30,"width":20,"height":10}
    status          VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_skus_product_id ON skus(product_id);
CREATE INDEX idx_skus_attributes ON skus USING GIN(attributes);

-- Product images
CREATE TABLE product_images (
    id              BIGSERIAL PRIMARY KEY,
    product_id      UUID NOT NULL REFERENCES products(product_id),
    sku_id          VARCHAR(100) REFERENCES skus(sku_id),
    image_url       VARCHAR(500) NOT NULL,
    resolution      VARCHAR(20) NOT NULL,  -- 'thumbnail','medium','large','original'
    sort_order      INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_product_images_product ON product_images(product_id, sort_order);

-- Categories (hierarchical using closure table)
CREATE TABLE categories (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(200) NOT NULL UNIQUE,
    parent_id       INT REFERENCES categories(id)
);
```

### 12.2 Inventory Schema

```sql
-- Inventory per SKU per warehouse
CREATE TABLE inventory (
    sku_id              VARCHAR(100) NOT NULL,
    warehouse_id        INT NOT NULL,
    quantity_on_hand    INT NOT NULL DEFAULT 0,
    quantity_reserved   INT NOT NULL DEFAULT 0,
    quantity_available  INT GENERATED ALWAYS AS (quantity_on_hand - quantity_reserved) STORED,
    reorder_point       INT NOT NULL DEFAULT 10,
    last_updated        TIMESTAMP NOT NULL DEFAULT NOW(),
    version             BIGINT NOT NULL DEFAULT 0,  -- for optimistic locking
    PRIMARY KEY (sku_id, warehouse_id),
    CONSTRAINT chk_non_negative_available CHECK (quantity_on_hand >= quantity_reserved),
    CONSTRAINT chk_non_negative_on_hand CHECK (quantity_on_hand >= 0)
);

CREATE INDEX idx_inventory_sku ON inventory(sku_id, quantity_available) 
    WHERE quantity_available > 0;

-- Inventory reservations
CREATE TABLE inventory_reservations (
    reservation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku_id              VARCHAR(100) NOT NULL,
    warehouse_id        INT NOT NULL,
    quantity            INT NOT NULL DEFAULT 1,
    order_id            UUID,  -- NULL until order is created
    cart_id             UUID,
    user_id             UUID,
    status              VARCHAR(50) NOT NULL DEFAULT 'active',
    -- active | confirmed | cancelled | expired
    expires_at          TIMESTAMP NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (sku_id, warehouse_id) REFERENCES inventory(sku_id, warehouse_id)
);

CREATE INDEX idx_reservations_sku_warehouse 
    ON inventory_reservations(sku_id, warehouse_id, status);
CREATE INDEX idx_reservations_order ON inventory_reservations(order_id);
CREATE INDEX idx_reservations_cart ON inventory_reservations(cart_id);
CREATE INDEX idx_reservations_expiry 
    ON inventory_reservations(expires_at) WHERE status = 'active';

-- Warehouses
CREATE TABLE warehouses (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    address         JSONB NOT NULL,
    latitude        DECIMAL(9,6) NOT NULL,
    longitude       DECIMAL(9,6) NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'active'
);
```

### 12.3 Order Schema

```sql
-- Orders
CREATE TABLE orders (
    order_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'pending',
    subtotal_cents  BIGINT NOT NULL,
    tax_cents       BIGINT NOT NULL DEFAULT 0,
    shipping_cents  BIGINT NOT NULL DEFAULT 0,
    total_cents     BIGINT NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    payment_id      VARCHAR(200),  -- payment gateway transaction ID
    idempotency_key VARCHAR(200) UNIQUE NOT NULL,
    shipping_address JSONB NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id ON orders(user_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders(status, created_at);
CREATE INDEX idx_orders_idempotency ON orders(idempotency_key);

-- Order line items
CREATE TABLE order_items (
    id              BIGSERIAL PRIMARY KEY,
    order_id        UUID NOT NULL REFERENCES orders(order_id),
    sku_id          VARCHAR(100) NOT NULL,
    product_id      UUID NOT NULL,
    quantity        INT NOT NULL,
    unit_price_cents BIGINT NOT NULL,
    warehouse_id    INT,  -- fulfillment warehouse
    tracking_number VARCHAR(200),
    fulfillment_status VARCHAR(50) DEFAULT 'pending',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_sku ON order_items(sku_id);

-- Order events (event sourcing)
CREATE TABLE order_events (
    id              BIGSERIAL PRIMARY KEY,
    order_id        UUID NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    event_data      JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    actor_type      VARCHAR(50),  -- 'user', 'system', 'operator'
    actor_id        VARCHAR(200)
);

CREATE INDEX idx_order_events_order ON order_events(order_id, occurred_at);
CREATE INDEX idx_order_events_type ON order_events(event_type, occurred_at);
```

### 12.4 Cart Schema

```sql
-- Persistent cart (PostgreSQL backup for Redis)
CREATE TABLE carts (
    cart_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID,  -- NULL for anonymous carts
    session_id      VARCHAR(200),  -- anonymous session
    status          VARCHAR(50) NOT NULL DEFAULT 'active',
    -- active | checked_out | abandoned | merged
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_carts_user ON carts(user_id) WHERE status = 'active';
CREATE INDEX idx_carts_session ON carts(session_id) WHERE status = 'active';

CREATE TABLE cart_items (
    id              BIGSERIAL PRIMARY KEY,
    cart_id         UUID NOT NULL REFERENCES carts(cart_id),
    sku_id          VARCHAR(100) NOT NULL,
    product_id      UUID NOT NULL,
    quantity        INT NOT NULL DEFAULT 1,
    price_snapshot_cents BIGINT NOT NULL,  -- price when item was added
    added_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(cart_id, sku_id)
);

CREATE INDEX idx_cart_items_cart ON cart_items(cart_id);
```

---

## Part 13: REST API Design

### 13.1 Product Catalog API

```
GET /v1/products/{product_id}
  Response 200:
  {
    "product_id": "B08N5WRWNW",
    "title": "Echo Dot (4th Gen)",
    "description": "...",
    "brand": "Amazon",
    "category": {"id": 123, "name": "Smart Speakers", "path": "Electronics > Smart Home"},
    "skus": [
      {
        "sku_id": "B08N5WRWNW-BK",
        "attributes": {"color": "Charcoal"},
        "price": {"amount": 49.99, "currency": "USD", "type": "base"},
        "flash_price": null,
        "availability": {"status": "in_stock", "count_display": "In Stock"}
      }
    ],
    "images": [
      {"url": "https://cdn.example.com/products/B08N5WRWNW-01.jpg", "resolution": "large"},
      {"url": "https://cdn.example.com/products/B08N5WRWNW-01-thumb.jpg", "resolution": "thumbnail"}
    ],
    "average_rating": 4.7,
    "review_count": 152847
  }

GET /v1/search/products?q={query}&category={id}&min_price={price}&max_price={price}
              &brand={brand}&min_rating={rating}&prime_only={bool}
              &sort={relevance|price_asc|price_desc|avg_rating|newest}
              &page={num}&page_size={size}
  Response 200:
  {
    "results": [...],         // array of product summaries
    "total_count": 4521,
    "facets": {
      "brands": [{"name": "Sony", "count": 234}, ...],
      "price_ranges": [{"label": "Under $50", "count": 891}, ...],
      "avg_rating": [{"label": "4+ Stars", "count": 2341}, ...]
    },
    "page": 1,
    "page_size": 20
  }
```

### 13.2 Inventory API

```
GET /v1/inventory/{sku_id}
  Response 200:
  {
    "sku_id": "B08N5WRWNW-BK",
    "total_available": 842,
    "can_ship_by": "2024-01-17",     // soonest ship date across warehouses
    "warehouses": [                   // only returned for internal callers
      {"warehouse_id": 7, "available": 400, "ship_days": 2},
      {"warehouse_id": 12, "available": 442, "ship_days": 1}
    ]
  }

POST /v1/inventory/reserve
  Request:
  {
    "items": [
      {"sku_id": "B08N5WRWNW-BK", "quantity": 1}
    ],
    "cart_id": "cart-uuid",
    "user_id": "user-uuid",
    "idempotency_key": "reserve-cart-uuid-timestamp"
  }
  Response 200:
  {
    "reservation_id": "res-uuid",
    "status": "reserved",
    "expires_at": "2024-01-16T14:30:00Z",
    "items": [
      {"sku_id": "B08N5WRWNW-BK", "quantity": 1, "warehouse_id": 12}
    ]
  }
  Response 409 (insufficient inventory):
  {
    "error": "INSUFFICIENT_INVENTORY",
    "unavailable_items": [{"sku_id": "B08N5WRWNW-BK", "requested": 1, "available": 0}]
  }

POST /v1/inventory/confirm
  Request:
  {
    "reservation_id": "res-uuid",
    "order_id": "order-uuid",
    "idempotency_key": "confirm-order-uuid"
  }
  Response 200: {"status": "confirmed"}

POST /v1/inventory/release
  Request:
  {
    "reservation_id": "res-uuid",
    "reason": "payment_failed"
  }
  Response 200: {"status": "released"}
```

### 13.3 Cart API

```
GET /v1/carts/{cart_id}
  Response 200:
  {
    "cart_id": "cart-uuid",
    "items": [
      {
        "sku_id": "B08N5WRWNW-BK",
        "product_id": "B08N5WRWNW",
        "quantity": 1,
        "current_price": {"amount": 49.99, "currency": "USD"},
        "snapshot_price": {"amount": 54.99, "currency": "USD"},
        "price_change": {"direction": "down", "amount": 5.00},
        "availability": "in_stock"
      }
    ],
    "subtotal": {"amount": 49.99, "currency": "USD"},
    "item_count": 1,
    "expires_at": "2024-02-15T10:00:00Z"
  }

POST /v1/carts/{cart_id}/items
  Request:
  {
    "sku_id": "B08N5WRWNW-BK",
    "quantity": 1
  }
  Response 200: { ...updated cart... }

PUT /v1/carts/{cart_id}/items/{sku_id}
  Request: {"quantity": 2}
  Response 200: { ...updated cart... }

DELETE /v1/carts/{cart_id}/items/{sku_id}
  Response 204

POST /v1/carts/merge
  Request:
  {
    "source_cart_id": "anon-cart-uuid",   // anonymous cart
    "target_cart_id": "user-cart-uuid"    // authenticated user's cart
  }
  Response 200: { ...merged cart... }
```

### 13.4 Checkout API

```
POST /v1/checkout/initiate
  Request:
  {
    "cart_id": "cart-uuid",
    "user_id": "user-uuid",
    "shipping_address": {
      "name": "John Doe",
      "street1": "123 Main St",
      "city": "Seattle",
      "state": "WA",
      "postal_code": "98101",
      "country": "US"
    },
    "payment_method_id": "pm_visa_xxxx4242",
    "idempotency_key": "checkout-cart-uuid-timestamp"
  }
  Response 202 (Accepted — saga started):
  {
    "checkout_id": "checkout-uuid",
    "status": "processing",
    "poll_url": "/v1/checkout/checkout-uuid/status"
  }

GET /v1/checkout/{checkout_id}/status
  Response 200:
  {
    "checkout_id": "checkout-uuid",
    "status": "completed",          // processing | completed | failed
    "order_id": "order-uuid",       // present if completed
    "error": null,                  // present if failed
    "steps": [
      {"step": "inventory_reserved", "status": "success", "at": "2024-01-16T12:00:01Z"},
      {"step": "payment_processed", "status": "success", "at": "2024-01-16T12:00:02Z"},
      {"step": "order_confirmed", "status": "success", "at": "2024-01-16T12:00:02Z"}
    ]
  }

GET /v1/orders/{order_id}
  Response 200:
  {
    "order_id": "order-uuid",
    "status": "shipped",
    "items": [...],
    "shipments": [
      {
        "shipment_id": "ship-uuid",
        "warehouse_id": 12,
        "items": [...],
        "tracking_number": "1Z999AA1012345678",
        "carrier": "UPS",
        "estimated_delivery": "2024-01-18",
        "status": "in_transit"
      }
    ],
    "total": {"amount": 55.98, "currency": "USD"},
    "created_at": "2024-01-16T12:00:00Z"
  }
```

---

## Part 14: High-Level Architecture Diagram

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    Client Layer                          │
                    │     Browser / Mobile App / Third-party Sellers           │
                    └──────────────────────┬──────────────────────────────────┘
                                           │ HTTPS
                                           ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │              CDN + WAF + Load Balancer                   │
                    │    (Static assets, images served from CDN edge)          │
                    │    (DDoS protection, rate limiting at edge)              │
                    └──────────────────────┬──────────────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────────────────┐
                    │                      ▼                                   │
                    │          ┌───────────────────────┐                      │
                    │          │     API Gateway         │                      │
                    │          │  (auth, routing,        │                      │
                    │          │   rate limiting)        │                      │
                    │          └───────────┬─────────────┘                     │
                    │                      │                                   │
                    │    ┌─────────────────┼──────────────────────────────┐   │
                    │    │                 │                              │   │
                    │    ▼                 ▼                              ▼   │
                    │ ┌────────┐    ┌──────────┐    ┌───────────┐  ┌──────┐  │
                    │ │Catalog │    │Inventory │    │  Cart     │  │Order │  │
                    │ │Service │    │Service   │    │  Service  │  │Mgmt  │  │
                    │ └───┬────┘    └────┬─────┘    └─────┬─────┘  └──┬───┘  │
                    │     │              │                │           │      │
                    │     ▼              ▼                ▼           ▼      │
                    │ ┌───────┐    ┌──────────┐   ┌────────┐  ┌──────────┐  │
                    │ │DynamoDB│   │PostgreSQL│   │ Redis  │  │PostgreSQL│  │
                    │ │(prods) │   │+ Redis   │   │(carts) │  │ (orders) │  │
                    │ └───────┘   │(inventory│   └────────┘  └──────────┘  │
                    │             │ counters)│                              │
                    │             └──────────┘                              │
                    │                                                        │
                    │    ┌─────────────────────────────────────────────┐    │
                    │    │              Search Service                   │    │
                    │    │         (Elasticsearch Cluster)               │    │
                    │    └─────────────────────────────────────────────┘    │
                    │                                                        │
                    │    ┌─────────────────────────────────────────────┐    │
                    │    │           Checkout Saga Orchestrator          │    │
                    │    │   (coordinates inventory + payment + order)   │    │
                    │    └─────────────────────────────────────────────┘    │
                    │                                                        │
                    │    ┌──────────────────┐    ┌──────────────────────┐   │
                    │    │  Payment Gateway  │    │  Fulfillment Service  │   │
                    │    │  (Stripe/Braintree│    │  (warehouse routing,  │   │
                    │    │   external)       │    │   shipping labels)    │   │
                    │    └──────────────────┘    └──────────────────────┘   │
                    │                                                        │
                    │    ┌─────────────────────────────────────────────┐    │
                    │    │                  Kafka                        │    │
                    │    │   (order events, inventory events, catalog    │    │
                    │    │    change events, cart events)                │    │
                    │    └─────────────────────────────────────────────┘    │
                    └────────────────────────────────────────────────────────┘
```

---

## Part 15: Flash Sale System — Complete Architecture

### 15.1 Pre-Sale System Walkthrough

The flash sale architecture needs to be explained end-to-end because it touches every
part of the system. Here is the complete sequence for a well-designed flash sale:

**Preparation Phase (T-24h to T-0):**

1. Marketing team creates sale configuration: product IDs, sale prices, inventory
   allocation per warehouse, sale window (start time, end time).
2. Catalog service pre-populates CDN with sale product pages. Each edge location
   in CloudFront gets a cached copy of the product page HTML and images.
3. Inventory service seeds Redis counters: for each sale SKU, `SET inventory:flash:{sku_id} {quantity}`. This is the atomic counter that gates purchases.
4. Virtual waiting room service is initialized with the sale configuration.
5. All A/B tests and non-essential features are disabled for the sale duration.
6. Auto-scaling groups scale to 3x normal capacity.

**Sale Opening (T=0):**

1. The sale page goes live. CDN serves the cached sale page to millions of users
   simultaneously from edge nodes — no origin servers involved.
2. Users click "Buy Now." The request hits the API gateway.
3. API gateway checks if the user has a valid access token (issued by the virtual
   waiting room). Users without tokens are redirected to the waiting room.
4. Users in the waiting room see their queue position and estimated wait time.

**Purchase Flow (per admitted user):**

1. User with access token submits "Buy Now." Cart service creates a single-item cart.
2. Checkout service generates an idempotency key and calls the inventory service.
3. Inventory service executes the Lua atomic check-and-decrement on the Redis
   counter. If successful (returns 1), a reservation record is created in PostgreSQL
   (asynchronously, via Kafka event). If the counter is already 0, returns "sold out."
4. If inventory was reserved, the checkout saga proceeds to payment.
5. Payment is processed via the external gateway.
6. On payment success, the reservation is confirmed. The Redis counter is NOT
   incremented back — the decrement is permanent for confirmed purchases.
7. Order is created, fulfillment is triggered, confirmation email is sent.

**Compensation Flow:**

1. If payment fails, the inventory service increments the Redis counter back by 1:
   `INCR inventory:flash:{sku_id}`. This releases the unit for the next buyer.
2. If the sale ends before all inventory is purchased (unlikely but possible), the
   remaining Redis counter value is reconciled with the PostgreSQL source of truth.

### 15.2 Reconciliation After the Sale

After a flash sale, the Redis counter and the PostgreSQL inventory table must be
reconciled. The Redis counter decrements may not perfectly match confirmed purchases
because: some payments fail (causing counter increments back), some reservations
expire without payment, and (in extreme cases) Redis may have had a brief unavailability.

The reconciliation process: after the sale window closes, a reconciliation job reads
all confirmed purchase records from PostgreSQL, sums the quantities sold per SKU,
and compares to the initial inventory minus the current Redis counter. Any discrepancy
is investigated: a counter higher than expected means units were released back that
should not have been (payment failure handling bug); a counter lower than expected
means units were sold without a corresponding PostgreSQL record (outbox processing
lag). The latter is the more dangerous case: those units are in-flight and the
PostgreSQL record will eventually be created by the outbox relay. The reconciliation
job waits 10 minutes after the sale ends before running to allow all in-flight
events to settle.

---

## Part 16: Observability and Monitoring

### 16.1 Key Metrics

Every component of the e-commerce system has specific metrics that must be monitored
in real time, with alerting thresholds defined before any major sale event.

**Inventory Service:**
- `inventory.reservation.success_rate` — Should stay above 95% for available SKUs;
  drops below 95% indicate a Redis connectivity issue, not genuine sold-out status.
- `inventory.reservation.latency_p99` — Should be under 10 ms; spikes indicate Redis
  backpressure or a Lua script contention issue.
- `inventory.counter.negative_values` — Should be 0 at all times; any negative value
  indicates a race condition in the compensation logic.

**Checkout Saga:**
- `checkout.saga.completion_rate` — Percentage of initiated checkouts that complete
  successfully. Normal: 85–90%. Below 80% triggers an alert.
- `checkout.payment.failure_rate` — Normal: 2–5%. Spikes indicate payment gateway
  issues or fraud pattern changes.
- `checkout.compensation.execution_rate` — How often compensating transactions run.
  Should be low; spikes indicate a systematic failure in one Saga step.

**Cart Service:**
- `cart.merge.success_rate` — Should be 100%. Failures indicate a Redis transaction
  issue during anonymous-to-authenticated merge.
- `cart.abandonment_rate` — Business metric, but operationally useful: sudden spikes
  may indicate a checkout UX bug or a payment issue.

**Flash Sale Specific:**
- `flash_sale.queue_depth` — Current depth of the virtual waiting room queue.
  Monitored in real time to adjust admission rate.
- `flash_sale.inventory_drain_rate` — Units sold per second. Compared to target rate
  to detect if the sale is going faster or slower than planned.
- `flash_sale.oversell_count` — Should be exactly 0 at all times. Any value above 0
  is a severity-1 incident.

### 16.2 Distributed Tracing

All requests in the e-commerce system carry a `trace_id` header from the API gateway
through every downstream service call. The checkout saga, in particular, benefits
enormously from distributed tracing: when a checkout fails, the operator can pull
up the trace and see exactly which step failed, how long each step took, and what
error was returned. Without tracing, debugging a failed checkout saga in a
microservices architecture requires correlating logs across 6+ services by timestamp,
which is error-prone and slow.

The trace is propagated via the W3C Trace Context standard (`traceparent` header).
All Kafka events include the trace context in the event headers, allowing the trace
to span asynchronous message processing. Jaeger or Zipkin is the typical trace
storage and visualization system.

---

## Part 17: L5 vs. L6 Calibration

| Dimension | L5 (Senior Engineer) | L6 (Staff Engineer) |
|-----------|---------------------|---------------------|
| **Inventory** | Knows reservation pattern, optimistic locking. Draws reserve/confirm flow. | Explains Redis DECR + Lua atomicity vs. SQL locking tradeoffs. Knows when each is appropriate. Handles Redis failure fallback. Quantifies the throughput difference (10M ops/sec vs. 10K ops/sec). |
| **Checkout** | Knows the steps need to be coordinated. Mentions rollback on failure. | Names the Saga pattern specifically. Distinguishes orchestrated vs. choreographed. Designs the saga state machine schema. Mentions Outbox pattern for reliable event publishing. |
| **Flash Sales** | Mentions Redis, queuing, rate limiting. | Designs the full pre-sale + virtual waiting room + atomic Lua script + post-sale reconciliation. Knows admission rate calculation. Handles Redis failure mid-sale. |
| **Search** | Elasticsearch for full-text search plus facets. | Designs the Elasticsearch mapping, explains BM25 ranking, designs the async sync pipeline from DynamoDB to Elasticsearch via Kafka. Discusses personalized re-ranking pipeline. |
| **Failure Modes** | Mentions "retry with exponential backoff." | Specifies idempotency key semantics at every layer. Distinguishes payment gateway idempotency (external) from internal service idempotency. Designs the compensation logic for each saga step. |
| **Data Model** | "Separate products table and inventory table." | Designs the full schema: product/SKU separation, inventory per warehouse with computed generated column, reservation TTL via indexed expiry column, order event sourcing table. |
| **Scale Numbers** | Rough estimates: "a lot of products, a lot of orders." | Memorizes and uses specific numbers: 3M items/minute at Amazon peak, Shopify 75M requests in 30 minutes on Black Friday, Redis 10M ops/sec, SQL row lock throughput 10K ops/sec. |
| **Trade-off Framing** | "We can use X or Y, each has pros/cons." | Frames trade-offs as: "At 100K flash sale items/sec, SQL row locks give us ~10K ops/sec — 10x too slow. Redis DECR gives us 10M ops/sec — 100x headroom. The cost is managing the fallback when Redis is unavailable, which we handle with a feature-flag-gated SQL fallback at reduced capacity." |
| **Breadth** | Covers catalog, inventory, checkout well. May skip multi-warehouse, pricing complexity, recommendations. | Connects all subsystems: explains how the pricing engine output feeds both Elasticsearch (for sorting) and the cart (for price snapshots), how flash sale inventory depletion signals feed demand-forecasting for replenishment. |

---

## Part 18: Pre-Interview Drill

Before walking into an Amazon or Shopify system design interview, you should be
able to answer each of these questions fluently and in under 2 minutes each.

**1. What is the reservation pattern and why is it used for inventory?**

The reservation pattern is a two-phase approach: Phase 1 reserves the item (decrements
available, creates a reservation record with a TTL), and Phase 2 either confirms (on
payment success) or cancels (on payment failure or TTL expiry). It is used because
it separates the "intent to purchase" from the "actual purchase," giving the system
a recovery window (the TTL) for incomplete checkouts. Without reservations, the only
options are optimistic locking (which allows oversell under race conditions if not
implemented carefully) or pessimistic locking (which serializes all purchases and
kills throughput).

**2. Why does Redis DECR prevent oversell better than SQL UPDATE?**

Redis DECR is atomic at the Redis level — it is a single operation that both reads and
decrements the value with no interleaving. In contrast, a SQL `UPDATE ... WHERE count > 0`
requires the database to execute a read-modify-write under a row lock. Under high
concurrency, the SQL lock creates a serialization bottleneck and limits throughput to
~10K transactions per second per row. Redis DECR, with no locking overhead, can handle
over 10 million operations per second on a single node, making it 1000x more suitable
for flash sale inventory.

**3. What is the Saga pattern and when do you use it?**

The Saga pattern is a sequence of local transactions with compensating transactions
for failure recovery. It is used when a business transaction spans multiple services
or external systems (like a payment gateway) where a distributed transaction (2PC)
is not feasible. In checkout, the saga coordinates: reserve inventory → process
payment → confirm inventory → create order → trigger fulfillment. If any step fails,
the saga executes compensating transactions in reverse order to undo the work done.

**4. Explain idempotency in the checkout context. What breaks without it?**

Without idempotency, a network timeout between the checkout service and the payment
gateway causes the customer to retry, potentially being charged twice. Idempotency
keys solve this: a unique key (UUID tied to the checkout session) is sent with the
payment request. The payment gateway records the key and the response. If the same
key is received again (retry), the gateway returns the original response without
re-processing. The same principle applies to inventory reservation: a reservation
with the same idempotency key should be a no-op if the reservation already exists.

**5. How does the virtual waiting room work and what does it protect?**

The virtual waiting room queues users at the entry point to the checkout flow, admitting
them at a controlled rate. It protects: the inventory service (prevents thundering herd
against Redis), the payment service (prevents overwhelming the payment gateway's TPS
limits), and the order database (prevents a burst of concurrent writes). Users in the
queue receive a queue position and estimated wait time. Admitted users receive a
short-lived access token (JWT, 10-minute TTL) that allows them to proceed through
checkout. The admission rate is set to match the downstream capacity (typically 5–10x
the maximum purchase completion rate, accounting for the fact that not all admitted
users complete a purchase).

**6. How do you handle anonymous cart to authenticated cart merging?**

At login time: fetch both the anonymous cart (identified by session ID) and the
authenticated user's existing cart (identified by user ID). Merge strategy: for
SKUs present in only one cart, add them to the merged result. For SKUs present in
both carts, use the maximum quantity (not the sum). Execute the merge atomically using
a Redis transaction (MULTI/EXEC). After the merge, expire the anonymous cart key and
update the authenticated user's cart key. Record a CartMerged event for analytics.

**7. Describe the Elasticsearch query for "wireless headphones under $100, 4+ stars,
prime eligible, sorted by relevance."**

Uses a `bool` query with: a `must` clause containing a `multi_match` across title,
brand, description, and tags with field-level boosting (title 3x, brand 2x). A
`filter` clause with term filters for `prime_eligible: true`, range filter for
`price: {lte: 100}`, and range for `average_rating: {gte: 4}`. The `filter` clause
does not affect scoring — it only narrows the result set — which is correct because
these are binary criteria, not relevance signals. Sorting by `_score` (BM25 relevance)
descending, with `popularity_score` as tiebreaker. Add `aggs` for facet counts.

**8. What is the Outbox pattern and why is it needed in the order service?**

The Outbox pattern ensures that database writes and event publishing are atomic.
Without it: the order is written to the DB, and then the service crashes before
publishing the event to Kafka. The order exists but the fulfillment service never
receives it. With the Outbox: the order record and an outbox event row are written
in a single DB transaction. A relay service polls the outbox table and publishes
rows to Kafka, marking them as published. If the relay crashes, it restarts and
replays unpublished rows. The event is guaranteed to be published exactly once (or
at-least-once with idempotent consumers).

**9. How does multi-warehouse inventory affect the checkout flow?**

The reservation step must select a specific warehouse for each SKU. The selection
algorithm scores warehouses by proximity to the shipping address (delivery time),
current stock level (avoid draining one warehouse while others have surplus), and
shipping cost. The selected warehouse ID is recorded in the reservation. When
fulfillment is triggered after checkout, the order is routed to the reserved warehouse.
If an order contains items from multiple warehouses, the OMS creates multiple fulfillment
records (one per warehouse), each with its own tracking number. The customer sees a
multi-package order.

**10. What happens to the system during a Redis cluster failover mid-sale?**

Sentinel or Cluster detects the primary failure and elects a new primary within
seconds (typically 5–15 seconds). During the failover window, inventory reservation
requests that cannot reach Redis fail closed (return "inventory unavailable") rather
than open (return "inventory available"). This may result in a brief period of false
"sold out" responses — slightly underselling — which is acceptable. Overselling
(accepting reservations when there is no inventory) is not acceptable, so fail-closed
is the correct default. After failover, the new Redis primary may have a slightly
lower counter value than the true inventory (if a few DECRs from the last seconds
before the primary failed were not replicated to the replica). This minor discrepancy
is reconciled by the post-sale reconciliation job.

**11. Design the pricing engine query for a Prime member seeing a flash sale item.**

The pricing engine query evaluates price tiers in priority order. For a Prime member
during a flash sale:
1. Check for an active flash sale price: `WHERE price_type = 'flash' AND valid_from <= NOW() AND (valid_until IS NULL OR valid_until > NOW())`.
2. If flash price exists, return it (highest priority).
3. Else, check for Prime member price.
4. Else, return base price.
The logic is implemented as a single SQL query with ORDER BY on price type priority
and LIMIT 1, or as a cached lookup in Redis (populated when the flash sale is
configured). During flash sales, prices are pre-cached in Redis to avoid any DB
latency on the hot path.

**12. What is the "product vs. SKU" distinction and why does it matter for inventory?**

A "product" is the conceptual item (Nike Air Max 270 Shoe). A "SKU" is a specific
purchasable variant (Nike Air Max 270 Shoe, Size 10, Black). One product has many
SKUs. Inventory is tracked per SKU (you have 50 size-10 Black shoes, not just
"50 Air Max 270s"). Search and display are at the product level (show one product
card, not 50 SKU cards). The product page dynamically shows availability per variant
by querying inventory for all SKUs of the product. This separation is critical:
searching by product allows deduplication in results; purchasing a SKU ensures the
correct item is reserved.

---

## Part 19: Common Interview Mistakes

### Mistake 1: Treating Inventory as a Simple Counter

Many candidates say "just use a SQL UPDATE to decrement the count." This fails to
address concurrency, oversell, and scale. The correct answer involves the reservation
pattern (for the general case) and Redis atomic operations (for flash sales). Always
pair the solution with the scale numbers to justify the technology choice.

### Mistake 2: Forgetting Idempotency in Checkout

Checkout can be retried by the client (network timeout), retried by the Saga
orchestrator (service crash and recovery), and retried at the payment layer (intermittent
payment gateway error). Without idempotency keys at each layer, retries cause
double-charges, double-inventory-decrements, and duplicate orders. Any checkout
design without explicit idempotency handling is incomplete at the Staff level.

### Mistake 3: Using a Distributed Transaction for Checkout

Candidates who know about 2PC (two-phase commit) sometimes suggest "use a distributed
transaction across the order DB, inventory DB, and payment gateway." This fails because
the payment gateway is an external system that does not participate in distributed
transactions. The Saga pattern with compensating transactions is the correct answer.
Distinguish between the Saga as the pattern (correct) and 2PC as the implementation
(incorrect for this use case).

### Mistake 4: Not Discussing the Flash Sale as a Special Case

If the interview mentions "flash sale" or "peak traffic spike" and you respond with
the same architecture as normal traffic, you are failing to scope the problem. Flash
sales require: virtual waiting room (to throttle traffic), pre-warmed caches (to avoid
cold-start failures), Redis-based inventory counters (not SQL), and a post-sale
reconciliation step. These are specific, named patterns. Demonstrate you know them.

### Mistake 5: Ignoring the Anonymous-to-Authenticated Cart Transition

Cart merging is a deceptively tricky edge case that interviewers love because it
reveals whether you have actually thought about user journeys or just the happy path.
The mistake is either ignoring it entirely or choosing the wrong merge strategy
(overwriting the authenticated cart loses the user's work; summing quantities
double-counts items already in both carts). The correct answer: merge with
deduplication, taking the maximum quantity for items in both carts.

### Mistake 6: Sizing the Elasticsearch Cluster as a Single Node

Elasticsearch cannot run as a single node at Amazon-scale product catalog size (350M+
documents). The index must be sharded across multiple nodes. A common approach: 10
primary shards with 1 replica each (20 total shards), distributed across a 20-node
cluster. The index is further partitioned by category for the largest categories
(Electronics, Apparel) to avoid hotspots. Failing to mention sharding implies you
have not thought about scale, which is a red flag at the Staff level.

### Mistake 7: Not Explaining the Reservation TTL Expiry Mechanism

The reservation TTL is not just a conceptual idea — it requires a mechanism to
actually expire reservations and return inventory to the available pool. Saying "the
reservation expires after 15 minutes" without explaining how is incomplete. The
correct answer: use Redis EXPIRE on the reservation key (the key expiry triggers
a Redis keyspace notification, consumed by a listener that increments the inventory
counter back). Or: run a scheduled cleanup job that queries `WHERE status = 'active'
AND expires_at < NOW()` and releases expired reservations. The Redis EXPIRE approach
is more real-time; the cleanup job approach is simpler to implement and more
operationally transparent.

---

## Part 20: Exercises and Homework

### Exercise 1: Design the Flash Sale Inventory Counter in Redis

Implement (in pseudocode or Python) a complete Redis-backed inventory counter for
a flash sale with:
- Atomic Lua script for check-and-decrement
- Idempotency via reservation ID tracking
- TTL-based expiry with keyspace notifications to auto-release expired reservations
- A compensation function for failed payments
- A reconciliation function to compare Redis state with PostgreSQL source of truth

### Exercise 2: Draw the Checkout Saga State Machine

For the checkout Saga described in Part 6, draw a complete state diagram including:
- All happy-path states and transitions
- All failure states (PaymentFailed, InventoryUnavailable, FulfillmentFailed)
- All compensating transitions (what happens when each failure occurs)
- The Saga's stored state schema (what columns does the saga_state table have?)

### Exercise 3: Design the Cart Merge Algorithm

Write pseudocode for the anonymous-to-authenticated cart merge operation that:
- Handles duplicate SKUs (same SKU in both carts)
- Handles price changes since items were added
- Handles sold-out items (present in the anonymous cart but no longer in stock)
- Executes atomically using Redis transactions
- Records a CartMerged event for analytics

### Exercise 4: Size the Elasticsearch Cluster

Given: 500 million product documents, average document size 2 KB, query throughput
of 50,000 search queries per second, p99 latency target of 50 ms. Size the
Elasticsearch cluster: how many nodes? How many shards? How much storage per node?
What replication factor? Justify your numbers.

### Exercise 5: Design the Multi-Warehouse Routing Algorithm

Given: a customer in Seattle, WA placing an order with 3 items. Item A: available
in Seattle (1 day), San Francisco (2 days), Dallas (5 days). Item B: available in
Denver (3 days), Dallas (4 days). Item C: available only in New Jersey (7 days).
Design the algorithm to select warehouses minimizing total delivery time while
considering shipping cost. When should the system use a split shipment vs. a single
shipment from a more distant warehouse?

### Exercise 6: Implement the Pricing Engine Query

Write the SQL query and Redis caching logic for the pricing engine that:
- Returns the correct price for a given SKU and user context (Prime member, business
  account, or standard customer)
- Applies the flash sale price if an active flash sale exists for this SKU
- Falls back through price tier hierarchy correctly
- Caches the result in Redis with an appropriate TTL
- Invalidates the cache when a price is updated

---

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              KEY TAKEAWAYS                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. DECOMPOSE FIRST: "Design Amazon" = 4 systems: catalog (CDN + ES +        │
│     DynamoDB), inventory (reservation + Redis), cart (Redis + PostgreSQL),    │
│     checkout (Saga pattern). Say this out loud before drawing anything.       │
│                                                                              │
│  2. RESERVATION PATTERN: Reserve on add-to-cart (TTL 15 min), confirm on    │
│     payment success, auto-release on TTL expiry. This is the standard        │
│     solution for general inventory. Do not use simple decrements.            │
│                                                                              │
│  3. REDIS FOR FLASH SALES: DECR is atomic. Lua scripts make                  │
│     check-and-decrement atomic. 10M ops/sec vs. SQL's 10K ops/sec —          │
│     1000x difference. Pre-seed counters, use Lua, reconcile after.           │
│                                                                              │
│  4. SAGA PATTERN FOR CHECKOUT: Not a distributed transaction. A sequence     │
│     of local transactions with compensating transactions for failure         │
│     recovery. Add idempotency keys at every layer to prevent double-charges. │
│                                                                              │
│  5. VIRTUAL WAITING ROOM: Throttles admission to the checkout flow.          │
│     Protects Redis, payment gateway, and order DB from thundering herd.      │
│     Admission rate = downstream capacity / expected conversion rate.         │
│                                                                              │
│  6. ELASTICSEARCH FOR SEARCH: BM25 + faceted aggregations in one query.      │
│     Async sync from primary DB via Kafka. Re-rank top-100 with               │
│     personalization signals. Shard by category at Amazon scale.              │
│                                                                              │
│  7. THE NUMBERS: Amazon 3M items/minute peak. Shopify 75M req in 30 min     │
│     on Black Friday 2021. Redis 10M ops/sec. SQL row lock ~10K ops/sec.      │
│     Checkout p99 < 2 sec. Inventory hold TTL 15 min. Cart TTL 30 days.       │
│                                                                              │
│  8. OUTBOX PATTERN: Write event to outbox table in same DB transaction as    │
│     the business record. Relay service publishes to Kafka asynchronously.    │
│     Guarantees events are published even if the service crashes.             │
│                                                                              │
│  9. PRODUCT vs. SKU: Products are display units (one card in search).        │
│     SKUs are purchase units (specific size/color variant). Inventory is      │
│     per SKU per warehouse. Never track inventory at the product level.       │
│                                                                              │
│ 10. MULTI-WAREHOUSE: Score each warehouse by proximity + stock level +       │
│     shipping cost. Record warehouse assignment in the reservation. Split     │
│     shipments are the norm, not the exception, at Amazon scale.              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

E-commerce system design at Staff/L6 level requires cleanly separating four
sub-systems with very different consistency and availability requirements: the
product catalog (read-heavy, CDN + Elasticsearch + DynamoDB, eventual consistency
fine), inventory (strong consistency required, reservation pattern for general case,
Redis atomic DECR + Lua for flash sales), the shopping cart (session state in Redis,
persistent backup in PostgreSQL, anonymous-to-authenticated merge at login), and
checkout (Saga pattern with compensating transactions, idempotency keys at every
layer, Outbox pattern for reliable event publishing).

Flash sales are the forcing function that exposes every architectural weakness:
SQL row locks are insufficient at 100K ops/sec; you need Redis atomic operations.
Thundering herds overwhelm any downstream service; you need a virtual waiting room.
Post-sale reconciliation is required to ensure the Redis counters match the
PostgreSQL source of truth.

The numbers that anchor this system: Amazon processes 3 million items per minute
at Prime Day peak. Shopify served 75 million requests in 30 minutes on Black Friday
2021. Redis handles 10 million operations per second. SQL row locking handles roughly
10,000 operations per second. These numbers are the justification for every technology
choice in the flash sale architecture.

---

*Chapter 106. Pairs with Chapter 105 (Fraud Detection) and Chapter 70 (Payment Systems).*
*Section 6: Staff/L6 System Design Case Studies.*

---

## Interview Simulation — E-commerce / Inventory (Staff / L6)

*45-minute Staff-level system design interview. Phases follow the Section 2 framework.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design the inventory management system for an e-commerce platform at Amazon scale. Where do you start?

**Candidate:** A few scoping questions. First — are we designing inventory tracking only, or also the order fulfillment workflow (picking, packing, shipping)? Second — do we need to support flash sales, meaning inventory goes from 10,000 units to 0 in under 1 minute? Third — do we operate multiple warehouses, and does the system need to route orders to the nearest warehouse with stock? Fourth — are we the marketplace operator (like Amazon selling its own inventory) or a platform for third-party sellers (where each seller manages their own stock)?

> **Interviewer:** Multi-warehouse, first-party inventory. Flash sales are a critical requirement — a product can sell out in seconds. Third-party sellers are future scope. Focus on preventing oversells and handling peak traffic.

**Candidate:** Functional requirements: (1) Display accurate available inventory to buyers. (2) Reserve inventory on add-to-cart (soft reservation). (3) Commit inventory on purchase (hard allocation). (4) Release reservations on cart expiry or checkout abandonment. (5) Route orders to the closest warehouse with available stock. Non-functional: inventory reads at < 5 ms p99, reservation operations at < 50 ms p99, zero oversells (hard constraint), handle 100,000 orders/second during flash sales.

---

### Phase 2: Estimation (4 min)

**Candidate:** Normal operations: 10 million daily orders ÷ 86,400 s ≈ 116 orders/s average. Flash sale peak: assume a single product, 1 million buyers hitting "buy" in the first 10 seconds → 100,000 requests/s on a single SKU. That's the number to design for. Inventory read traffic: 100× write traffic (browsing vs purchasing) → 10 million reads/s peak, fully cacheable in Redis. Reservation records: 1 million concurrent carts × 5 items average = 5 million active reservations, each ~100 bytes → 500 MB, easily fits in Redis. Warehouse routing: 10 warehouses, each with ~100,000 SKUs → inventory matrix is 1 million records, ~200 MB in RAM — fits in memory tier.

---

### Phase 3: API Design (4 min)

**Candidate:** Four core operations. `GET /v1/inventory/{sku_id}` returns `{available_qty, reserved_qty, warehouse_breakdown}` — served from cache, never from DB on read path. `POST /v1/cart/{cart_id}/reserve` body `{sku_id, qty}` — creates a soft reservation, returns reservation_id and expiry_time (15 min). `POST /v1/order/{order_id}/commit` — converts reservation to hard allocation, returns warehouse assignment. `DELETE /v1/cart/{cart_id}/reserve/{reservation_id}` — explicit release; also triggered automatically on expiry. Idempotency key required on reserve and commit operations — if the network retries, we return the same reservation_id instead of creating a duplicate.

> **Interviewer:** Why separate reserve and commit instead of a single "buy" operation?

**Candidate:** Separating reserve from commit models the real business flow: the buyer adds to cart (reserve), then goes through a multi-step checkout (address, payment) that takes 1–5 minutes. If we don't reserve on add-to-cart, the buyer reaches the payment step and finds the item is out of stock — terrible UX. If we do a hard commit on add-to-cart, we prevent others from buying during the entire checkout flow even if this buyer abandons. Soft reservation with an expiry is the industry-standard solution: hold the inventory for 15 minutes, release it if checkout is not completed.

---

### Phase 4: Data Model (4 min)

**Candidate:** Two storage tiers. Source of truth (PostgreSQL with row-level locking): `inventory` table — `sku_id, warehouse_id, on_hand_qty, reserved_qty, available_qty` (available = on_hand - reserved), with a CHECK constraint `available_qty >= 0`. `reservations` table — `reservation_id, sku_id, warehouse_id, qty, cart_id, expires_at, status` (ACTIVE/COMMITTED/RELEASED). We use `SELECT ... FOR UPDATE` on the inventory row to serialize concurrent reservation attempts. Hot cache (Redis): `inv:{sku_id}` → hash of available_qty per warehouse. Updated via a change-data-capture stream from PostgreSQL (Debezium → Kafka → Redis consumer). Read path hits Redis; write path hits PostgreSQL. The Redis value is eventually consistent — acceptable for display, but reservation decisions are made against PostgreSQL.

---

### Phase 5: HLD + Deep Dive (20 min)

```
INVENTORY READ PATH (browsing)
================================
Buyer App → API Gateway → Inventory Read Service
  │
  ▼
Redis Cache (inv:{sku_id}, TTL 30s)
  │ HIT (99%+): return available_qty
  │ MISS: read PostgreSQL replica → populate cache
  ▼
PostgreSQL Read Replica

RESERVATION PATH (add to cart)
================================
Buyer App → API Gateway → Reservation Service
  │
  ▼
Redis Idempotency Check (dedup retry within 30s)
  │
  ▼
PostgreSQL Primary
  BEGIN;
  SELECT available_qty FROM inventory
    WHERE sku_id=? AND warehouse_id=?
    FOR UPDATE;           -- row-level lock
  -- if available_qty >= requested_qty:
  UPDATE inventory SET available_qty = available_qty - qty,
                       reserved_qty  = reserved_qty  + qty;
  INSERT INTO reservations (...);
  COMMIT;
  │
  ▼
Kafka Event: inventory.reserved
  → Cache Invalidation Consumer (update Redis)
  → Expiry Worker (scheduled job: release expired reservations)

FLASH SALE PATH
================
Buyer App
  │
  ▼
Flash Sale Queue (SQS FIFO, per-SKU queue)
  │ rate-limited ingest: 100K req/s → queue
  │ queue depth = available inventory units
  │
  ▼
Queue Consumer (single-threaded per SKU)
  │ pops N requests, runs batch reservation in PostgreSQL
  │ accepted: reservation confirmation to buyer
  │ rejected (queue exhausted): sold-out notification
  │
  └─► No direct DB contention during the spike

WAREHOUSE ROUTING
==================
Commit Service (on order payment)
  │
  ▼
Routing Engine
  │ query: which warehouses have available_qty >= ordered_qty?
  │ rank by: shipping_distance_score + fulfillment_SLA_score
  │ assign to closest warehouse with stock
  ▼
Hard Allocation (UPDATE inventory, INSERT shipment_assignment)
```

**Deep Dive 1: Oversell Prevention — The Core Problem.**

The CHECK constraint `available_qty >= 0` in PostgreSQL is the last line of defense. But at 100,000 concurrent reservation attempts on a single SKU, row-level locking becomes the bottleneck — PostgreSQL can handle ~10,000 row-locked transactions/second on a single row. For flash sales, the queue-based approach is essential: we funnel all requests for a single SKU through a FIFO queue, with queue depth equal to available inventory. The queue consumer is single-threaded per SKU, so there is zero lock contention at the database level. The queue acts as a serialization point. Alternative approach: inventory counter in Redis with DECRBY atomic operation — Redis can handle 500,000 atomic decrements/second. We use Redis as the tentative reservation (decrement to 0 = sold out, reject further decrements) and PostgreSQL as the durable record. This is a two-phase approach: Redis is the "fast path" gate, PostgreSQL is the durable commit.

> **Interviewer:** With the Redis fast-path approach, what happens if the PostgreSQL write fails after the Redis decrement?

**Candidate:** *(Cross-question: Redis/PostgreSQL consistency)* This is the split-brain scenario. Redis says "sold," PostgreSQL says "unsold." Recovery: we use a saga pattern. Step 1: decrement Redis counter (tentative reservation). Step 2: write to PostgreSQL. If step 2 fails, a compensating transaction increments Redis back (rollback). We wrap this in an outbox pattern: the reservation service writes to a local `reservation_outbox` table in PostgreSQL atomically with the inventory update. A Debezium CDC stream reads the outbox and updates Redis. This means PostgreSQL is the source of truth and Redis is derived — we never have a state where Redis is decremented but PostgreSQL has no record. Latency cost: ~5 ms extra for the PostgreSQL write before confirming to the user. Worth it for correctness.

**Deep Dive 2: Flash Sale Traffic Spike — Queue-Based Ordering.**

The flash sale problem is not just about inventory correctness — it's about the web tier surviving the spike. 1 million users hitting "buy" simultaneously will overwhelm the API servers (C10M problem) before they even reach the database. Three defenses: First, CDN-level rate limiting — Cloudflare Workers enforce a token bucket per IP, throttling to 10 requests/s per IP before the spike reaches origin. Second, virtual waiting room — users who arrive during the spike get a queue position page (static HTML, served by CDN) and receive a position token. When their token is called, they get a 60-second window to complete checkout. This prevents the stampede from reaching the reservation service. Third, inventory pre-announcement — for known flash sales, we pre-configure the SQS queue with a capacity equal to available inventory. Once the queue is full, subsequent requests immediately get "sold out" without touching any backend service.

> **Interviewer:** How does price history and catalog versioning interact with inventory?

**Candidate:** *(Cross-question: price and catalog consistency with inventory)* Price changes and catalog updates (new images, descriptions) are separate from inventory mutations. Price is stored in a `price_history` table (`sku_id, price, effective_from, effective_to`) — we never update a price record, we only INSERT new records. This gives us a full audit trail (important for regulatory compliance and dispute resolution) and allows us to query "what was the price at time T?" without complex CDC archaeology. At checkout, the price is locked at the price at add-to-cart time (stored in the reservation record) — this protects buyers from price increases during checkout. Catalog versioning uses a similar approach: `catalog_versions` table, current version pointer in Redis. The buyer's cart stores the version_id at the time of add-to-cart; if the catalog version changes, we show a "product updated, please review your cart" notice.

---

### Common Cross-Questions and Strong Answers (Staff Level)

**Q: How do you handle returns — an item is returned to Warehouse B but was originally sold from Warehouse A?**
A: Returns create new inventory records at the receiving warehouse regardless of origin. When a return is received and inspected, we run an `INSERT` into inventory for the return's warehouse with quantity +1, and update the original order status to RETURNED. We do NOT attempt to "undo" the original warehouse's debit — that would create a reconciliation nightmare. The receiving warehouse's on_hand_qty increases, making the unit available for resale. Return processing triggers a cache invalidation for that SKU's inventory display.

**Q: Your PostgreSQL primary is at 95% CPU during a Black Friday flash sale. What do you do?**
A: Immediate mitigation: activate the queue-based path (if not already on), which shifts the serialization point from PostgreSQL row locks to SQS. Reduce the reservation TTL from 15 min to 5 min to accelerate expiry-release cycles. Enable read shedding: drop non-critical read queries (analytics, reporting) from hitting the replica. Medium-term: add a read replica specifically for the inventory display path (separate from the reservation replica). The root cause is likely write amplification from too many concurrent long-running transactions — check for lock wait time in `pg_stat_activity` and kill stale transactions. Pre-Black-Friday: run load tests at 3× expected peak with the queue architecture.

**Q: How do you detect and prevent inventory hoarding (bots adding thousands of items to cart to prevent competitors from buying)?**
A: Three controls. Reservation cap per account per SKU per day (e.g., max 5 reservations, prevents bulk holding). Velocity check: if an account creates > 20 reservations in 60 s, flag for CAPTCHA or temporary block. Reservation conversion rate: if an account has > 500 expired reservations with < 5% checkout conversion, the account is flagged for review (bot-like behavior). These signals feed into the trust & safety platform — similar to fraud detection, they run as a lightweight check in the Reservation Service before creating the reservation record.

---

*Chapter 106. Pairs with Chapter 105 (Fraud Detection) and Chapter 70 (Payment Systems).*
*Section 6: Staff/L6 System Design Case Studies.*
