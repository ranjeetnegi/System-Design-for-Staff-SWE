# Chapter 61d: Hotel Reservation System — Airbnb / Booking.com

> The hardest part of booking a hotel room is not the UI. It is making sure
> two people trying to book the last room at the same millisecond do not both
> get a confirmation — while still being fast enough that nobody notices
> the database is working hard.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Hotel Reservation System                   |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify (hotel rooms, flights, rental cars?)        |
|  Min 2-9:   Users & use cases                                    |
|  Min 9-16:  Functional requirements                              |
|  Min 16-21: Scale math                                           |
|  Min 21-26: Non-functional requirements                          |
|  Min 26-29: Assumptions                                          |
|  Min 29-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                            |
|                                                                  |
|  Key numbers to know:                                            |
|  - Booking.com: 500K+ hotels, 1.5M room-nights/day             |
|  - Airbnb: 7M listings worldwide                                 |
|  - Peak: holiday weekends, Black Friday hotel deals             |
|  - Booking window: 1 night to 12 months in advance             |
|  - Average stay: 2.3 nights                                      |
|  - Cancellation rate: 30-40% (hotels overbook because of this)  |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Optimistic locking to prevent double-booking                 |
|  - Idempotency key for retry safety                             |
|  - Pre-populated inventory table                                 |
|  - Redis cache for availability search                           |
|  - Single region, MySQL + Redis                                  |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Sharding strategy for inventory table (hot hotels)           |
|  - Multi-region with conflict resolution                         |
|  - Dynamic pricing + ML-based overbooking rate                  |
|  - Saga pattern for distributed payment + booking atomicity     |
|  - Overbooking policy with automatic walk compensation          |
+------------------------------------------------------------------+
```

---

## Phase 1: Users and Use Cases (Minutes 2-9)

### Who uses a hotel reservation system?

Think of a hotel reservation system like a bank vault with many safety deposit boxes. Each box (room) can only be opened by one person at a time. The tricky part: thousands of people are trying to grab the same boxes simultaneously, and you cannot let two people think they own the same box.

**Human users:**
- Travelers browsing hotels, checking availability, making bookings
- Business travelers booking on behalf of their company
- Hotel managers viewing current reservations, managing room inventory
- Customer support agents modifying or cancelling reservations on behalf of guests

**System users (L5 signal):**
- Mobile apps: issue availability searches and booking requests
- Payment service: called by booking service to charge the guest
- Notification service: receives booking events, sends confirmation emails and SMS
- Analytics pipeline: receives booking events to compute revenue metrics
- Review system: receives check-out events to prompt guests for reviews
- Pricing engine: reads booking patterns to adjust room prices dynamically

**Operational users:**
- SRE: monitors booking success rate, latency, double-booking alerts
- Hotel operations: bulk-load hotel and room inventory data
- Finance: reconciles bookings with payment records

### Core use cases

**P0 — Must have:**
- UC1: Search for available rooms at a hotel for a date range
- UC2: Book a specific room for a date range (atomic, no double-booking)
- UC3: Cancel a reservation (with inventory release)
- UC4: View my reservations (history and upcoming)

**P1 — Important:**
- UC5: Modify reservation dates (within hotel policy)
- UC6: View hotel details (amenities, location, photos)
- UC7: Receive confirmation email after successful booking

**Out of scope for L5:**
- Review and rating system
- Dynamic pricing algorithm
- Multi-currency and tax calculation
- Hotel management portal (adding/removing rooms)
- Third-party channel integration (OTA connections)

### Edge cases with architecture implications

- **The last room race**: Two users simultaneously try to book the last available room. Both check availability (room available), both attempt to book. Without proper locking, both get a confirmation. This forces optimistic or pessimistic locking in the booking flow.
- **Multi-night booking**: A guest books 3 nights. Each night must be available. The check must span multiple inventory rows atomically.
- **Retry on network failure**: User clicks "Book", the network drops. Client retries. Without idempotency, the guest is charged and booked twice. Forces idempotency key design.
- **Cancellation window edge case**: Guest cancels at exactly the boundary of the free cancellation window (48 hours before check-in). Forces precise timestamp comparison, not just date comparison.
- **Overbooking**: Hotels deliberately sell more rooms than they have, because 30-40% of guests cancel. If overbooking percentage is wrong and all guests show up, someone must be "walked" (sent to another hotel at the hotel's expense).

### Alignment check

> "I am designing a hotel room reservation system — like Booking.com. The core operations are: search for available rooms for a date range, book a room (preventing double-booking under concurrency), and cancel a reservation. Payment processing is a separate system — I will treat it as a black box. I will design for strong consistency on bookings (no double-booking is a hard requirement) and eventual consistency for availability search (showing a room as available when it just became reserved within the last 5 seconds is acceptable). Does that match your intent?"

---

## Phase 2: Functional Requirements (Minutes 9-16)

### Read flows

- **F1 — Search hotels**: `search_hotels(city, check_in, check_out, guests) -> list of hotels with available rooms`
- **F2 — Check room availability**: `check_availability(hotel_id, room_type, check_in, check_out) -> {available: bool, price, room_count}`
- **F3 — View reservation**: `get_reservation(reservation_id) -> full reservation details`
- **F4 — View my reservations**: `list_reservations(user_id) -> list of reservations (past + upcoming)`

### Write flows

- **F5 — Book room**: `book_room(user_id, room_id, check_in, check_out, idempotency_key) -> reservation_id`
  - Must be atomic: either books successfully or fails cleanly, never partial
- **F6 — Cancel reservation**: `cancel_reservation(reservation_id, user_id) -> {success, refund_amount}`
  - Must release inventory atomically with the cancellation
- **F7 — Modify reservation**: `modify_reservation(reservation_id, new_check_in, new_check_out) -> updated_reservation`
  - Implemented as: cancel + rebook (simpler than partial modification)

### Control flows (L5 signal)

- **F8 — Inventory lock during booking**: Before confirming, the system must atomically check and decrement available inventory. If inventory check and decrement are not atomic, double-booking occurs.
- **F9 — Payment trigger**: After successful booking, trigger payment charge. If payment fails, release the inventory (compensating transaction).
- **F10 — Reservation expiry**: If payment is not received within 15 minutes of booking, automatically cancel and release inventory. Prevents rooms being held indefinitely by abandoned bookings.
- **F11 — Cancellation policy enforcement**: Check hotel's cancellation policy before allowing free cancellation. Enforce the refund calculation.

---

## Phase 3: Scale and Capacity (Minutes 16-21)

### User scale

- Hotels: 500,000 hotels globally
- Rooms per hotel: average 50 rooms, 5 room types = 250 rooms per hotel
- Total rooms: 500K × 250 = 125 million rooms
- DAU searching: 10 million users
- Daily bookings: 1.5 million room-nights per day

### Activity scale

```
Searches per day:
  10M DAU * 3 searches/user = 30M searches/day
  30M / 86,400 = 347 searches/sec average
  Peak (Friday evening): 5x = 1,735 searches/sec

Bookings per day:
  1.5M room-nights/day / 2.3 nights per booking = 652K bookings/day
  652K / 86,400 = 7.5 bookings/sec average
  Peak (holiday weekend booking surge): 10x = 75 bookings/sec

Read/write ratio: 347 / 7.5 = ~46:1 for search:booking
  Search is massively read-heavy -> cache aggressively
  Bookings are low volume but high stakes -> strong consistency

Inventory table size:
  Pre-populate every room for every date up to 1 year ahead:
  500K hotels * 5 room types * 365 days = 912M rows
  Per row: room_id (8B) + date (4B) + total_rooms (2B) + reserved_rooms (2B) = 16 bytes
  Total: 912M * 16 bytes = 14.6 GB (fits in sharded MySQL with room to spare)

Reservations table size:
  652K bookings/day * 365 days = 238M reservations/year
  Per row: ~200 bytes
  Total: 238M * 200 bytes = 47.6 GB per year (keep 3 years hot = 143 GB)

Availability cache (Redis):
  Cache key: "avail:{room_id}:{date}" = ~30 bytes per key
  Cache value: available_count (integer) = 4 bytes
  Active dates: 500K hotels * 5 room types * 30 days ahead = 75M active keys
  Total: 75M * 34 bytes = 2.55 GB (easily fits in Redis)
```

### What breaks first at 10x

```
At 75 bookings/sec (current peak) vs 750 bookings/sec (10x):

1. Inventory table row contention:
   Popular hotels (Marriott NYC, Christmas Eve) have hundreds of
   concurrent booking attempts on the same inventory rows.
   Optimistic locking retry rate spikes from 2% to 30%.
   Fix: per-hotel booking queue (serialize writes per hotel)
   or partitioned inventory table with row-level locks.

2. MySQL connection pool exhaustion:
   Each booking holds a transaction for ~100ms (read + update + insert)
   750 concurrent bookings * 100ms = 75 transaction-seconds/sec
   If connection pool = 200 connections: 75 / 200 = 0.375 transactions/connection/sec
   -> Barely fine at 10x. Add read replicas, connection pooling proxy (PgBouncer/ProxySQL).

3. Availability cache write rate:
   Each booking invalidates cache for all nights in the stay:
   750 bookings/sec * 2.3 nights = 1,725 cache deletes/sec
   Redis handles 500K ops/sec -> trivial.
```

### Design target

- Availability search: p50 = 50ms, p99 = 500ms (with cache hit)
- Booking: p50 = 300ms, p99 = 1,000ms (database transaction + payment trigger)
- Cancellation: p50 = 200ms, p99 = 800ms

---

## Phase 4: Non-Functional Requirements (Minutes 21-26)

### Latency targets

- Availability search (F2): p99 < 500ms (mostly served from Redis cache)
- Booking (F5): p99 < 1,000ms (database transaction, cannot be cached)
- Cancellation (F6): p99 < 800ms

### Availability

- Search: 99.99% (4 nines — search outage = no revenue)
- Booking: 99.9% (3 nines — booking outage is worse but brief outage more acceptable than stale search)
- Why different? Search can be served from cache even if DB is slow. Booking requires DB.

### Consistency model

- **Booking: STRONG CONSISTENCY** (mandatory). Double-booking is a business disaster — a guest shows up at a hotel with no room, the hotel must "walk" them (comp them a room at another hotel). This is both expensive (costs the hotel) and a reputation disaster. Strong consistency is non-negotiable here.
- **Availability search: EVENTUAL CONSISTENCY** (acceptable). If the availability cache is 5 seconds behind the database, a user might see a room as available that was just booked. They will discover this when they try to book (the booking will fail). This is the "optimistic" UX: show slightly stale availability, enforce at booking time.
- **Trade-off explicitly stated**: "I am sacrificing search accuracy (allow up to 5s stale) for search performance (cache serving 99% of searches). I enforce correctness at booking time with a database transaction."

### Durability

- Reservations: replicated 3 ways, written to durable storage before confirmation returned to user. A confirmed reservation must never be lost.
- Payment records: owned by the payment service (out of scope), but our system must not confirm a booking unless payment is durably recorded.

### Trade-offs to state out loud

> "I am using optimistic locking (not pessimistic) for most bookings because it has higher throughput — no lock is held during the booking flow, so concurrent bookings for different rooms do not block each other. The trade-off is retry overhead when two users compete for the same room simultaneously. I will switch to pessimistic locking (SELECT FOR UPDATE) only when the available count is 1 (last room) — that is the highest-stakes race condition and the retry loop is acceptable there."

---

## Phase 5: Assumptions and Constraints (Minutes 26-29)

### Assumptions

- A1: Each booking is for exactly one room type at one hotel. Multi-hotel bookings are multiple independent bookings.
- A2: Payment is handled by an external payment service (like Stripe). Our system calls the payment API but does not implement payment internals.
- A3: Room availability is pre-populated for up to 365 days in advance. Bookings further out are not supported.
- A4: Currency is single (USD). Multi-currency is a future extension.
- A5: Hotel room count per type is stable (hotels rarely add/remove physical rooms).

### Constraints

- C1: No double-booking — this is a hard requirement, not a trade-off
- C2: Confirmed reservation must survive system failures (durable)
- C3: Single region deployment (L5 scope)

### Simplifications

- S1: Hotel search (find hotels in a city) is handled by a separate geo-search service (similar to Ch61c). This chapter focuses on availability + booking, not hotel discovery.
- S2: Price calculation is a read from a pricing table — no dynamic pricing algorithm in scope.
- S3: "Modify reservation" is implemented as cancel + rebook to avoid the complexity of partial inventory adjustment.

---

## Architecture Design — HLD (Minutes 29-42)

### Opening analogy

Imagine a box office for a sold-out concert. One booth (the search counter) shows you which seats are still available — it has a display board that updates every few minutes (eventual consistency, from cache). A different booth (the booking counter) actually sells you the ticket. The booking counter has a direct line to the seat inventory and locks the seat the moment you say "yes" — before taking your money. If your credit card fails, the seat goes back on sale. The display board might not show that seat as available again for a few minutes, but the booking counter always has the real count.

That is our system: Redis-cached search (fast, slightly stale) + database-backed booking (slow, always correct).

### Full HLD ASCII diagram

```
[Guest App / Web]
        |
        | search / book / cancel
        v
+---------------------+
|    API GATEWAY      |
|  Auth, rate limit   |
|  Route to service   |
+---------------------+
        |
   +----+----+
   |         |
   v         v
+--------+  +----------+
| SEARCH |  | BOOKING  |
| SVC    |  | SVC      |
|        |  |          |
|Stateless| |Stateless |
+--------+  +----------+
   |              |
   |              |
   v              v
+-------+   +----------+
| Redis |   | MySQL    |
| Avail |   | Primary  |
| Cache |   |          |
| TTL   |   | reserv.  |
| 30s   |   | room_inv |
+-------+   | hotels   |
   ^         | rooms    |
   |         +----------+
   |              |
   | cache miss   | replication
   |              v
   |         +----------+
   +---------+ MySQL    |
             | Replica  |
             | (search  |
             |  reads)  |
             +----------+
                  |
                  | booking event
                  v
             +----------+
             | Kafka    |
             | Topic    |
             | booking- |
             | events   |
             +----------+
                  |
         +--------+--------+
         |                 |
         v                 v
  +------------+    +------------+
  | NOTIF SVC  |    | PAYMENT    |
  | (email/SMS)|    | SVC        |
  | Stateless  |    | Stateless  |
  +------------+    +------------+
```

### Component responsibilities table

```
+-------------------+----------------------------------+-----------+-------------------+
| Component         | Responsibility                   | Stateful? | Scale target      |
+-------------------+----------------------------------+-----------+-------------------+
| API Gateway       | Auth, rate limit, routing        | NO        | 2,000 req/sec     |
+-------------------+----------------------------------+-----------+-------------------+
| Search Service    | Query availability, return hotel | NO        | 1,735 req/sec     |
|                   | options; reads from Redis cache  |           | 5 instances       |
+-------------------+----------------------------------+-----------+-------------------+
| Booking Service   | Owns the booking transaction:    | NO        | 75 req/sec        |
|                   | lock check, insert reservation,  |           | 3 instances       |
|                   | trigger payment, publish event   |           |                   |
+-------------------+----------------------------------+-----------+-------------------+
| Redis (Avail)     | Availability count cache         | YES       | 2.55 GB RAM       |
|                   | Key: avail:{room_id}:{date}       |           | 30s TTL           |
|                   | Invalidated on book/cancel       |           | 1 instance + rep  |
+-------------------+----------------------------------+-----------+-------------------+
| MySQL Primary     | Source of truth: reservations,   | YES       | 75 writes/sec     |
|                   | room_inventory, hotels, rooms    |           | 200 connections   |
+-------------------+----------------------------------+-----------+-------------------+
| MySQL Replica     | Read replica for search fallback | YES       | 347 reads/sec     |
|                   | and reporting queries            |           |                   |
+-------------------+----------------------------------+-----------+-------------------+
| Kafka             | Booking event stream             | YES       | 75 events/sec     |
|                   | Consumers: notif, payment, analy |           | RF=3              |
+-------------------+----------------------------------+-----------+-------------------+
| Payment Service   | Charge guest (external SaaS)     | NO (ext)  | 75 calls/sec      |
+-------------------+----------------------------------+-----------+-------------------+
| Notification Svc  | Send confirmation email/SMS      | NO        | 75 msgs/sec       |
+-------------------+----------------------------------+-----------+-------------------+
```

### Write path: booking flow

```
Step 1: Client sends booking request
  POST /bookings
  {user_id, room_id, check_in, check_out, idempotency_key}
  (idempotency_key is a UUID generated by the client before sending)

Step 2: Booking Service checks idempotency
  SELECT * FROM reservations WHERE idempotency_key = ?
  If found: return existing reservation (this is a retry, not a new booking)
  If not found: proceed

Step 3: Acquire per-key Redis lock (prevents concurrent retries)
  SET lock:{idempotency_key} 1 NX PX 30000
  (NX = only set if not exists, PX 30000 = expire in 30 seconds)
  If lock not acquired: return 409 Conflict (another request in progress)

Step 4: Check availability (pre-flight, from cache)
  For each night in [check_in, check_out):
    val = Redis GET avail:{room_id}:{date}
    if val == 0: return 409 "Room not available" immediately
  (This is a fast rejection for obviously sold-out rooms; not the authoritative check)

Step 5: Begin database transaction
  START TRANSACTION

Step 6: Optimistic lock — the authoritative check + decrement
  For each night in [check_in, check_out):
    UPDATE room_inventory
    SET reserved_rooms = reserved_rooms + 1
    WHERE room_id = ? AND date = ?
    AND (total_rooms - reserved_rooms) > 0

  If any UPDATE returns 0 rows affected:
    ROLLBACK
    Return 409 "Room no longer available"
    (This is the core double-booking prevention)

Step 7: Insert reservation record
  INSERT INTO reservations
  (reservation_id, user_id, room_id, check_in, check_out,
   status='PENDING_PAYMENT', idempotency_key, created_at)

Step 8: Commit transaction
  COMMIT
  (Both the inventory decrement and the reservation insert are now durable)

Step 9: Trigger payment (async, via Kafka or synchronous call)
  Call Payment Service: charge(user_id, amount, idempotency_key)
  If payment succeeds:
    UPDATE reservations SET status='CONFIRMED' WHERE reservation_id = ?
    Publish to Kafka: {event="BOOKING_CONFIRMED", reservation_id, ...}
  If payment fails:
    ROLLBACK inventory: UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1
                         WHERE room_id = ? AND date = ? (for each night)
    UPDATE reservations SET status='PAYMENT_FAILED'
    Return 402 Payment Required

Step 10: Invalidate cache
  For each night in [check_in, check_out):
    Redis DEL avail:{room_id}:{date}
  (Or: DECR the counter — faster, but DEL is simpler and safer)

Step 11: Release idempotency lock
  Redis DEL lock:{idempotency_key}
```

### Read path: availability search

```
Step 1: Client requests availability
  GET /availability?room_id=123&check_in=2024-12-24&check_out=2024-12-27

Step 2: Search Service checks Redis for each night
  For each night in [check_in, check_out):
    val = Redis GET avail:{room_id}:{date}
    if val == null: cache miss -> go to Step 3
    if val == "0": not available, return immediately

Step 3: Cache miss -> query read replica
  SELECT date, (total_rooms - reserved_rooms) AS available
  FROM room_inventory
  WHERE room_id = ? AND date BETWEEN ? AND ?
  ORDER BY date

  For each returned row: Redis SET avail:{room_id}:{date} {available} EX 30
  (Cache for 30 seconds)

Step 4: Check all nights available
  If available_count > 0 for ALL nights: return available=true, price
  If any night has available_count == 0: return available=false

Step 5: Return to client
  {available: true, price_per_night: 150, total_price: 450, currency: "USD"}
```

### Key design decisions

```
+--------------------+-------------------------------+------------------+--------------------+
| Decision           | Why chosen                    | Rejected         | Trade-off          |
+--------------------+-------------------------------+------------------+--------------------+
| Optimistic locking | No lock held during tx. High  | Pessimistic      | Retry overhead     |
| (default)          | throughput for most cases     | (SELECT FOR      | when contention    |
|                    | (different rooms, diff dates) | UPDATE)          | is high (last rm)  |
+--------------------+-------------------------------+------------------+--------------------+
| Pre-populated      | O(1) UPDATE per night per     | Compute from     | 912M rows but      |
| room_inventory     | booking. No scan needed.      | reservations at  | only 14.6 GB.      |
| table              | Atomic row-level check.       | query time       | Nightly job adds   |
|                    |                               |                  | new day's rows.    |
+--------------------+-------------------------------+------------------+--------------------+
| MySQL (not NoSQL)  | Strong consistency via ACID   | Cassandra,       | Lower write        |
| for bookings       | transactions. Row-level locks.| DynamoDB         | throughput than    |
|                    | Well-understood semantics.    |                  | NoSQL but correct. |
+--------------------+-------------------------------+------------------+--------------------+
| Redis for avail    | Sub-millisecond reads.        | Query MySQL      | Stale data (30s    |
| cache (30s TTL)    | Absorbs 99% of search load.   | replica directly | TTL). User may     |
|                    | Simple invalidation on book.  |                  | see available room |
|                    |                               |                  | that was just      |
|                    |                               |                  | booked. Enforced   |
|                    |                               |                  | at booking time.   |
+--------------------+-------------------------------+------------------+--------------------+
| Idempotency key    | Client-generated UUID. Server | Server-generated | Client must        |
| (client-generated) | rejects duplicate inserts via | ID               | generate UUID.     |
|                    | unique constraint. Safe to    |                  | But server ID      |
|                    | retry on any network failure. |                  | cannot survive     |
|                    |                               |                  | connection drop.   |
+--------------------+-------------------------------+------------------+--------------------+
```

---

## Component-Level Design: Deep Dives

### Component 1: Room Inventory Table — the hot table

**Analogy:** Think of a concert hall with 50 rows of 20 seats each. Instead of tracking which specific seats are sold, you just track per row how many seats are sold. When someone buys 3 seats in row 15, you increment row 15's sold count by 3. You never need to scan all ticket records to know if seats are available in row 15 — you just check row 15's counter.

Our `room_inventory` table is that per-row counter, but for hotel rooms and dates.

**Schema:**

```
Table: room_inventory
+--------------+---------+---------+-----------+---------------+
| Column       | Type    | Size    | Index     | Notes         |
+--------------+---------+---------+-----------+---------------+
| room_id      | BIGINT  | 8 bytes | PK (part1)| FK to rooms   |
| date         | DATE    | 4 bytes | PK (part2)| The night     |
| total_rooms  | SMALLINT| 2 bytes |           | Physical count|
| reserved_rooms| SMALLINT| 2 bytes|           | Booked count  |
+--------------+---------+---------+-----------+---------------+
Primary Key: (room_id, date)

Derived: available = total_rooms - reserved_rooms
We do NOT store available as a column — it is always computed.
Why: storing available means three updates (total, reserved, available) instead of one.
     More columns to keep in sync = more bugs.
```

**Pre-population:**

```
On system startup (and nightly via a cron job):
  For each room (up to 125M rooms):
    For each date from TODAY to TODAY + 365:
      INSERT IGNORE INTO room_inventory (room_id, date, total_rooms, reserved_rooms)
      VALUES (?, ?, ?, 0)
      -- INSERT IGNORE: skip if row already exists (idempotent)

Total rows: 500K hotels * 5 room_types * 365 dates = 912M rows
Storage: 912M * 16 bytes = 14.6 GB
With index overhead (PK index): ~30 GB total
Sharded across 8 MySQL nodes: ~3.75 GB per node (trivial)

Nightly job: adds 1 day forward (365 days from tomorrow), removes expired dates
Job runtime: 125M room * 1 INSERT = ~2 minutes with batch insert
```

**The critical UPDATE:**

```
This single SQL statement is the core of double-booking prevention:

  UPDATE room_inventory
  SET reserved_rooms = reserved_rooms + 1
  WHERE room_id = ? AND date = ?
  AND (total_rooms - reserved_rooms) > 0

Why this is safe:
  1. MySQL row-level lock: this UPDATE acquires a row lock for the duration of the statement
  2. The condition (total_rooms - reserved_rooms) > 0 is checked INSIDE the locked row
  3. Two concurrent UPDATEs for the same (room_id, date):
     - First one acquires row lock, checks condition (passes), increments, releases lock
     - Second one acquires row lock, checks condition (may fail if room was last), returns 0 rows
  4. 0 rows affected = the room was just taken = ROLLBACK

For a 3-night stay, issue 3 UPDATEs (one per night) in a transaction.
If any UPDATE returns 0 rows: ROLLBACK all 3. The guest gets "sold out".
```

**Pessimistic locking for the "last room" scenario:**

```
When reserved_rooms = total_rooms - 1 (last available room):
  Use SELECT ... FOR UPDATE instead:

  BEGIN TRANSACTION
  SELECT * FROM room_inventory
  WHERE room_id = ? AND date = ?
  FOR UPDATE
  -- This acquires an exclusive row lock immediately
  -- All other transactions trying to book this room will wait here

  if (total_rooms - reserved_rooms) < 1:
    ROLLBACK
    return "sold out"

  UPDATE room_inventory
  SET reserved_rooms = reserved_rooms + 1
  WHERE room_id = ? AND date = ?

  INSERT INTO reservations ...
  COMMIT

Why pessimistic for last room:
  With optimistic locking and N concurrent last-room attempts:
  - All N read the inventory (available = 1)
  - All N issue the UPDATE
  - One succeeds, N-1 get 0 rows affected
  - N-1 retry -> likely fail again (now available = 0)
  - High retry rate, high database load, poor UX ("keep trying")
  
  With pessimistic locking and N concurrent last-room attempts:
  - One acquires lock, others wait (queued)
  - First completes: books the last room, releases lock
  - Others check: available = 0, return "sold out" cleanly
  - No retry needed, one clear winner
```

---

### Component 2: Idempotency Key — Retry Safety

**Analogy:** Imagine you are at a vending machine. You insert coins and press the button, but the machine makes a loud noise and you are not sure if it dispensed the item or not. A safe vending machine would remember "this person inserted coins with ID #ABC123 and I gave them chips" — so pressing the button again with the same ID just confirms "yes, you got your chips" without dispensing again.

Idempotency key is our way to make booking safe for retries. The key is generated by the client before making the request, and the same key is sent on every retry.

**Full idempotency flow:**

```
CLIENT side:
  idempotency_key = generate_uuid()  // Generate ONCE before any request
  max_retries = 3
  
  for attempt in 1..max_retries:
    response = POST /bookings {
      room_id, check_in, check_out,
      idempotency_key: idempotency_key  // Same key every time
    }
    
    if response.status == 200: return response  // Success
    if response.status == 409: return "sold out"  // No retry
    if response.status == 402: return "payment failed"  // No retry
    if response.status == 5xx: sleep(backoff), continue  // Retry
  
  return "please try again manually"

SERVER side (Booking Service):

function book_room(user_id, room_id, check_in, check_out, idempotency_key):
  
  // Step 1: Check if we already processed this request
  existing = SELECT * FROM reservations
             WHERE idempotency_key = ?
  if existing:
    return existing  // Idempotent: return same result as before
  
  // Step 2: Acquire distributed lock on this idempotency key
  // Prevents two in-flight requests with same key from racing
  lock_acquired = redis.SET("idemplock:" + idempotency_key, 1, NX, PX=30000)
  if not lock_acquired:
    return 409 "Request in progress"
  
  try:
    // Step 3: Run the actual booking transaction
    result = run_booking_transaction(user_id, room_id, check_in, check_out, idempotency_key)
    return result
  finally:
    // Step 4: Release the lock (whether we succeeded or failed)
    redis.DEL("idemplock:" + idempotency_key)
```

**The unique constraint on idempotency_key:**

```
In the reservations table:
  UNIQUE INDEX idx_idempotency (idempotency_key)

When we INSERT INTO reservations with an idempotency_key:
  If the key already exists: MySQL throws a Duplicate Key error
  In our code: catch Duplicate Key error -> SELECT the existing reservation -> return it

This is the final safety net: even if two requests with the same key race past
our Redis lock (e.g., if the lock acquisition is not atomic), the database
UNIQUE constraint ensures only one INSERT succeeds.
```

**What each response status means for the client:**

```
200 OK: Booking confirmed. Stop retrying.
409 Conflict (room sold out): Stop retrying. Show "room unavailable".
402 Payment Required: Stop retrying. Show payment failure message.
500 Internal Server Error: Retry with same idempotency_key.
503 Service Unavailable: Retry with same idempotency_key.
Network timeout: Retry with same idempotency_key.

Key insight: the client should NEVER generate a new idempotency_key on retry.
A new key = a new booking attempt = risk of double-booking.
The old key = safe retry = returns same result or creates booking exactly once.
```

---

### Component 3: Multi-Night Availability — The Date Range Query

**Analogy:** Checking if a hotel room is available for 5 nights is like asking "is the meeting room free every day this week?" You need to check each day individually AND all days must be free — not just some of them.

**The query challenge:**

For a 1-night stay: trivial.
For a 3-night stay (Dec 24, 25, 26): need Dec 24, Dec 25, AND Dec 26 all available.

**Naive SQL (wrong for multi-night):**

```
-- This returns rooms available on ANY of the nights, not ALL:
SELECT room_id FROM room_inventory
WHERE date BETWEEN '2024-12-24' AND '2024-12-26'
AND (total_rooms - reserved_rooms) > 0
-- WRONG: returns room if even 1 night is available
```

**Correct SQL (all nights must be available):**

```
SELECT room_id
FROM room_inventory
WHERE date >= '2024-12-24' AND date < '2024-12-27'  -- 3 nights
AND (total_rooms - reserved_rooms) > 0
GROUP BY room_id
HAVING COUNT(*) = 3  -- Must have 3 rows (all 3 nights) with availability

-- If room has only 2 available nights out of 3, COUNT(*) = 2, not 3 -> excluded
-- If room has 0 available on any night, that night's row doesn't pass the WHERE -> COUNT < 3
```

**Performance:**

```
Index on (room_id, date):
  For a 3-night query: scan 3 rows per room (index range scan)
  For a hotel with 5 room types: 3 * 5 = 15 rows total
  MySQL with covering index: 15 rows in microseconds

Cache strategy:
  Cache key: "avail:{room_id}:{date}" = available_count for that specific night
  For availability check: check Redis for each of the 3 nights separately
  All 3 cache hits: return answer in ~3ms (3 Redis RTTs)
  Any cache miss: fall through to MySQL replica, cache the result (30s TTL)
  
  Why per-night keys (not per-date-range keys)?
  A booking for Dec 24-26 invalidates: avail:room1:2024-12-24, avail:room1:2024-12-25, avail:room1:2024-12-26
  If we cached the full range: any 1-night booking anywhere in the range invalidates the entire range
  Per-night keys: only invalidate the nights that actually changed
```

**Redis pipeline for availability check:**

```
Without pipeline (3 separate round trips):
  RTT1: GET avail:room1:2024-12-24 -> 1ms
  RTT2: GET avail:room1:2024-12-25 -> 1ms
  RTT3: GET avail:room1:2024-12-26 -> 1ms
  Total: 3ms (serial)

With pipeline (1 round trip):
  pipeline = redis.pipeline()
  pipeline.get("avail:room1:2024-12-24")
  pipeline.get("avail:room1:2024-12-25")
  pipeline.get("avail:room1:2024-12-26")
  results = pipeline.execute()  // One round trip returns all 3
  Total: 1ms

For a 7-night stay: pipeline saves 6ms per request. Significant at scale.
```

---

### Component 4: Cancellation and the Saga Pattern

**Analogy:** Cancelling a hotel booking is like returning a product you bought with 3 separate payment methods. The store must: (1) accept the return, (2) put the item back on the shelf, (3) refund each payment method. If step 3 fails, you still have to put the item back on the shelf — you cannot un-return the product. But the refund failure needs to be retried separately.

**Happy path cancellation:**

```
Step 1: Verify ownership and policy
  SELECT * FROM reservations WHERE reservation_id = ? AND user_id = ?
  If not found: return 404
  If status = 'CANCELLED': return 409 "Already cancelled"
  If check_in < NOW() + 48h AND policy = 'FREE_CANCEL_48H': return 403 "Outside cancellation window"

Step 2: Begin transaction
  START TRANSACTION

Step 3: Mark reservation as cancelled
  UPDATE reservations SET status = 'CANCELLED', cancelled_at = NOW()
  WHERE reservation_id = ? AND status != 'CANCELLED'
  (Idempotent guard: skip if already cancelled)

Step 4: Release inventory
  For each night in [check_in, check_out):
    UPDATE room_inventory
    SET reserved_rooms = reserved_rooms - 1
    WHERE room_id = ? AND date = ?

Step 5: Commit transaction
  COMMIT
  (Reservation is cancelled AND inventory is released atomically)

Step 6: Trigger refund (outside transaction — this is the saga)
  Call Payment Service: refund(reservation_id, refund_amount)
  -- This call can fail independently of the database transaction
```

**Failure scenario and the Saga pattern:**

```
The problem:
  Steps 1-5 succeed (reservation cancelled, inventory released)
  Step 6 fails (payment service timeout)

  The room is back on the shelf (good). But the guest has not received their refund (bad).
  We cannot undo steps 1-5 (the room might already be re-booked).

Saga: compensating transaction for the failed refund

  After refund failure:
    UPDATE reservations SET refund_status = 'PENDING' WHERE reservation_id = ?
    Schedule retry: add to a "pending_refund" table

  Retry worker (runs every minute):
    SELECT * FROM pending_refunds WHERE next_retry_at < NOW() LIMIT 100
    For each: call Payment Service refund again
    If success: mark as 'REFUNDED'
    If fail: exponential backoff (1min, 5min, 30min, 2h, 12h, 48h)
    After 72 hours with no success: alert operations team for manual resolution

  Why not retry immediately?
    Payment service might be having an outage. Immediate retries amplify the problem.
    Exponential backoff gives it time to recover.

  Why not use a distributed transaction (2PC)?
    2PC would coordinate our database and the payment service atomically.
    But: payment service is external (Stripe/Braintree), does not participate in our 2PC.
    Saga is the correct pattern for cross-service operations with external dependencies.
```

**Cancellation policy enforcement:**

```
Policy: free cancellation if cancelled > 48 hours before check-in
        1-night penalty if cancelled within 48 hours

function calculate_refund_amount(reservation, cancelled_at):
  hours_before_checkin = (reservation.check_in - cancelled_at) / HOUR
  
  if hours_before_checkin > 48:
    return reservation.total_price  // Full refund
  
  nightly_rate = reservation.total_price / reservation.nights
  penalty = nightly_rate * 1  // 1-night penalty
  return max(0, reservation.total_price - penalty)
```

---

### Component 5: Overbooking — the Airline Trick

**Analogy:** Airlines routinely sell more seats than they have because they know from historical data that ~10% of passengers will not show up. Hotels do the same thing. A hotel with 100 rooms might sell 105 reservations, betting that 5 guests will cancel before arrival. If all 105 show up, the hotel must "walk" the extra guests — find them a room at another hotel and pay for their transfer. This is expensive, so the overbooking rate is carefully tuned.

**Implementation:**

```
In the room_inventory table:
  total_rooms is set to physical_rooms * (1 + overbooking_rate)

  Hotel has 100 physical rooms, 5% overbooking rate:
  total_rooms = 100 * 1.05 = 105 (stored as integer: 105)

  When all 105 reservations are made:
    reserved_rooms = 105
    (total_rooms - reserved_rooms) = 0 -> room shows as sold out
    BUT: 105 bookings exist for 100 physical rooms

When all guests show up:
  The hotel "walks" 5 guests:
    - Finds them equivalent or better rooms at nearby hotel
    - Covers all costs (transportation, room, meals if applicable)
    - Issues apology vouchers
  Cost: ~$300 per walked guest = $1,500 total
  Revenue from 5 extra bookings (prevented empty rooms): ~$750-1500
  Net: roughly break-even, but walking guests damages reputation heavily

Better approach: dynamic overbooking rate (L6 extension)
  Historical cancellation rate for this hotel in December: 35%
  Current overbooking: 5%
  ML model predicts: 38% cancellation rate for this booking window
  Increase overbooking to 8% (within safe margin)
  
  At L5: just mention overbooking exists, set a static 5% rate.
  At L6: adaptive rate based on ML-predicted cancellation probability.
```

---

## Deep Concept Explanations (SSE Cross-Questioning Targets)

### Concept 1: Optimistic vs Pessimistic Locking — Deep Comparison

An interviewer will probe: "Walk me through both locking strategies. What is the exact database mechanism for each?"

**Pessimistic locking:**

```
Philosophy: "I assume conflict is likely. I lock the row before I need it."

SQL mechanism:
  BEGIN TRANSACTION
  SELECT * FROM room_inventory
  WHERE room_id = ? AND date = ?
  FOR UPDATE  -- Acquires exclusive row lock NOW

  (Other transactions trying to SELECT FOR UPDATE or UPDATE this row WAIT HERE)

  if available_count > 0:
    UPDATE ... SET reserved_rooms = reserved_rooms + 1
    INSERT INTO reservations ...
    COMMIT
    -- Lock released on COMMIT
  else:
    ROLLBACK
    -- Lock released on ROLLBACK

Timeline for 3 concurrent bookings of the last room:
  T=0: Booking A acquires lock
  T=0: Booking B tries to acquire lock -> WAITS
  T=0: Booking C tries to acquire lock -> WAITS
  T=100ms: Booking A completes, releases lock
  T=100ms: Booking B acquires lock, checks: available=0 -> ROLLBACK
  T=100ms: Booking C acquires lock, checks: available=0 -> ROLLBACK
  Result: one winner (A), two clean rejections (B, C), no retries needed
```

**Optimistic locking:**

```
Philosophy: "I assume conflict is rare. I check after the fact."

SQL mechanism (no explicit lock acquisition):
  BEGIN TRANSACTION
  
  UPDATE room_inventory
  SET reserved_rooms = reserved_rooms + 1
  WHERE room_id = ? AND date = ?
  AND (total_rooms - reserved_rooms) > 0  -- Condition checked atomically

  rows_affected = check_affected_rows()
  
  if rows_affected == 0:
    ROLLBACK  -- Lost the race
    return "sold out"
  
  INSERT INTO reservations ...
  COMMIT

Timeline for 3 concurrent bookings of the last room:
  T=0: A, B, C all issue UPDATE simultaneously
  T=1ms: All 3 UPDATEs arrive at MySQL, serialized by row lock internally
  T=1ms: A's UPDATE: condition passes (available=1), reserved_rooms=1, returns 1 row
  T=1ms: B's UPDATE: condition fails (available=0), returns 0 rows -> ROLLBACK
  T=1ms: C's UPDATE: condition fails (available=0), returns 0 rows -> ROLLBACK
  Result: one winner (A), two clean rejections (B, C)
  B and C might retry (configured by application). On retry: same outcome (0 available).
```

**When to choose which:**

```
+-------------------+-------------------+-------------------+
| Scenario          | Optimistic        | Pessimistic       |
+-------------------+-------------------+-------------------+
| Most rooms        | Better: no lock   | Overkill: lock    |
| available,        | overhead, high    | held unnecessarily|
| low contention    | throughput        |                   |
+-------------------+-------------------+-------------------+
| Last room,        | Worse: high retry | Better: no retry  |
| high contention   | rate, many failed | needed, clear     |
|                   | UPDATEs           | winner            |
+-------------------+-------------------+-------------------+
| Holiday sale      | Worse: 100 users  | Better: queue     |
| (100 concurrent   | all try, 99 fail  | forms, 99 wait    |
| attempts)         | and retry         | and see sold out  |
+-------------------+-------------------+-------------------+

Hybrid approach (what real systems use):
  if available_rooms > 2: use optimistic locking
  if available_rooms <= 2: use pessimistic locking (SELECT FOR UPDATE)

  The threshold (2) is tunable. The idea: switch to pessimistic only when
  contention is likely to be high (near capacity).
```

---

### Concept 2: Why Pre-Populate the Inventory Table?

An interviewer will probe: "Why not just compute availability from the reservations table? 912M rows seems like a lot."

**Option A: Pre-populated inventory table (what we do)**

```
room_inventory table:
  (room_id, date) -> (total_rooms, reserved_rooms)

To book: UPDATE ... WHERE (total - reserved) > 0
  -> Single row update. O(1) operation. Row-level lock on 1 row per night.

To check availability: SELECT where (total - reserved) > 0
  -> Index lookup on (room_id, date). O(1) per night.

Storage: 912M rows * 16 bytes = 14.6 GB total
```

**Option B: Compute from reservations table (naive approach)**

```
reservations table:
  (reservation_id, room_id, check_in, check_out, status)

To check availability for room R on date D:
  SELECT COUNT(*) FROM reservations
  WHERE room_id = R
  AND check_in <= D AND check_out > D
  AND status = 'CONFIRMED'
  
  -> Scans ALL reservations for room R that overlap date D
  -> For a popular hotel: thousands of reservations per room per year
  -> At 100K searches/sec: 100K full table scans -> database melts

To book: must wrap entire read + check + insert in a transaction with a lock
  START TRANSACTION
  SELECT COUNT(*) ... FOR UPDATE  -- Lock ALL rows that overlap this date
  if count < total_rooms: INSERT INTO reservations
  COMMIT
  
  Locking thousands of rows per booking -> massive contention
  Even a single booking locks all past reservations for that room
```

**Why 912M rows is not actually scary:**

```
912M rows * 16 bytes = 14.6 GB

MySQL on a 32 GB machine: fits easily
Sharded across 8 nodes: 1.8 GB per node
Primary key (room_id, date): B-tree index for O(log n) lookups
The "nightly job adds 1 day": 125M new rows/day at 1M inserts/sec = 2 minutes

Compare to: 238M reservations/year growing without bound = 714M rows after 3 years
The pre-populated inventory table is SMALLER and FASTER than computing from reservations.
```

---

### Concept 3: Idempotency — The Exact Failure Scenarios It Covers

An interviewer will probe: "What exactly happens in each failure scenario? Walk me through them."

**Failure 1: Network drop before server receives request**

```
Client sends request. Network drops. Server never sees it.
Client retries with same idempotency_key.
Server receives request for the first time -> processes normally.
Result: One booking, one charge. Correct.
```

**Failure 2: Server processes request, crashes before responding**

```
Server receives request. Runs transaction. Commits reservation.
Server crashes before sending response.
Client retries with same idempotency_key.
New server instance receives request.
Checks: SELECT * FROM reservations WHERE idempotency_key = ? -> FOUND.
Returns the existing reservation.
Result: One booking, one charge. Correct.
```

**Failure 3: Server processes request, response lost in network**

```
Server receives request. Processes. Commits. Sends response.
Network drops the response. Client sees timeout.
Client retries with same idempotency_key.
Server checks idempotency -> FOUND -> returns existing reservation.
Result: One booking, one charge. Correct.
```

**Failure 4: Two in-flight requests with same key (client retry + original)**

```
Client sends request. Slow network: 10 second delay.
Client timeout fires at 5 seconds. Client retries with same key.
Now: two requests with same idempotency_key are in-flight simultaneously.

Without Redis lock: both hit the booking service, both see nothing in reservations table yet,
both start transactions, both try to insert with same idempotency_key.
One succeeds, one gets Duplicate Key error -> safely returns the winner's result.
Result: One booking. Correct.

With Redis lock: second request sees lock exists, returns 409 "Request in progress".
Client retries again after 30 seconds (lock TTL). By then, first request has completed.
Idempotency check finds existing reservation. Returns it.
Result: One booking. Correct.
```

---

### Concept 4: Sharding the Inventory Table at Scale

An interviewer will probe: "You have 912M rows across how many shards? How do you shard? What is the hot shard problem?"

**Shard by hotel_id:**

```
Why hotel_id?
  A booking for hotel H touches room_inventory rows for hotel H only.
  Sharding by hotel_id means all inventory updates for hotel H go to one shard.
  No cross-shard transactions for bookings.

Shard assignment:
  shard_id = hotel_id % NUM_SHARDS
  8 shards: shard_id = hotel_id % 8

Why NOT shard by room_id?
  A hotel has multiple room types. A multi-night booking touches multiple rows
  for the same hotel, same room type, different dates.
  Sharding by room_id would put different dates for the same room on different shards
  -> cross-shard transaction for a multi-night booking. Bad.

Why NOT shard by date?
  A booking for Dec 24-26 touches Dec 24, Dec 25, Dec 26.
  Sharding by date puts these on 3 different shards.
  -> 3-shard distributed transaction for a 3-night booking. Very bad.

Hotel_id sharding: all nights for a booking on the same shard. Single-shard transaction.
```

**Hot shard problem:**

```
Famous hotels (Marriott NYC Times Square, Burj Khalifa) have 10x-100x the traffic
of an average hotel. Holiday weekends: thousands of concurrent booking attempts.

Hotel_id % 8 puts "famous hotel" on shard 3, for example.
Shard 3 gets 50% of all booking load while other shards sit idle.

Detection: monitor writes_per_sec per shard. Alert if any shard > 3x average.

Fix 1: Dedicated shard for hot hotels
  Manual: move top-100 hotels by booking volume to dedicated shard
  Automatic: detect hot shard, migrate hotel to its own shard

Fix 2: Consistent hashing with virtual nodes
  Each hotel_id hashes to a position on the ring.
  Famous hotels naturally get a wider portion of the ring -> proportional load.
  Adding a shard for the famous hotel: move just keys between it and predecessor.

Fix 3: Booking queue per hotel (L6)
  Serialize all bookings for hotel H through a queue.
  Queue consumer processes bookings one at a time -> no lock contention at all.
  Trade-off: queued bookings have higher latency (100ms-500ms).
```

---

### Concept 5: Caching Strategy — When Stale is OK and When It Is Not

An interviewer will probe: "Your search cache has 30s TTL. A room was booked 10 seconds ago. User searches, sees room as available, tries to book — what happens?"

**The staleness scenario:**

```
T=0: Room booked. reserved_rooms = total_rooms.
T=0: Cache invalidated: Redis DEL avail:room1:2024-12-24 -> 0

But: What if cache invalidation fails?
  Redis is slow/down at T=0: DEL fails.
  Cache still shows old value (available = 1).

T=10s: User searches. Cache hit: "available = 1". Shows room as available.
T=12s: User clicks "Book".
T=12s: Booking Service issues UPDATE ... WHERE (total - reserved) > 0
T=12s: UPDATE returns 0 rows affected (reserved_rooms = total_rooms)
T=12s: Booking Service returns 409 "Room no longer available"
T=12s: User sees "Sorry, this room was just taken"

Result: stale cache caused a bad search result, but the booking was correctly rejected.
The database is the source of truth. The cache is an optimization, not the enforcer.
```

**Why this design is intentional:**

```
Option A (what we do): eventual consistency for search, strong consistency for booking
  - Search may show wrong availability for up to 30 seconds
  - Booking always uses the database -> always correct
  - User experience: "room just became unavailable" is understandable

Option B: strong consistency for search (always accurate)
  - Every search would require a database read (no caching)
  - 1,735 searches/sec = 1,735 DB reads/sec on top of booking load
  - At peak, database becomes the bottleneck for search, not just booking
  - p99 search latency: 500ms (database) vs 5ms (cache hit)
  - Not worth it: users do not expect search to be real-time accurate

The right answer to the interviewer:
  "I accept eventual consistency on search because the cost of strong consistency
  (no caching) outweighs the benefit. The booking endpoint enforces correctness.
  The worst case is the user sees an available room, tries to book, and gets a clean
  rejection message. This is the standard e-commerce UX pattern."
```

---

### Concept 6: Payment Integration — Preventing Orphaned Bookings

An interviewer will probe: "What happens if the payment fails after you've already decremented inventory?"

**The orphaned booking problem:**

```
Scenario:
  T=0: Inventory decremented (reserved_rooms + 1)
  T=0: Reservation inserted (status = PENDING_PAYMENT)
  T=100ms: Payment call fails (Stripe timeout)

  Result: Room is reserved in inventory but not paid for.
  If we do nothing: room is "stuck" — not available to other guests,
  but also not paid for. Revenue loss + occupied inventory.
```

**Solution 1: Synchronous payment (simpler, but risky)**

```
Include payment in the database transaction:
  START TRANSACTION
  UPDATE room_inventory ... (decrement)
  INSERT INTO reservations ... (PENDING_PAYMENT)
  // Now call payment API INSIDE the transaction
  result = payment_service.charge(amount, idempotency_key)
  if result.success:
    UPDATE reservations SET status = 'CONFIRMED'
    COMMIT
  else:
    ROLLBACK  // Undoes inventory decrement and reservation insert
  
  Problem: we are holding a database transaction open while waiting for an external API call.
  Payment API: average 500ms, p99 2000ms.
  Transaction held open for up to 2 seconds = row lock held for 2 seconds = contention.
  
  At 75 bookings/sec * 2s held = 150 concurrent open transactions. Connection pool exhausted.
  This does not scale.
```

**Solution 2: Two-phase approach with reservation expiry (better)**

```
Phase 1: Reserve inventory (fast, in DB transaction)
  START TRANSACTION
  UPDATE room_inventory ... (decrement)
  INSERT INTO reservations (status='PENDING_PAYMENT', expires_at=NOW()+15min)
  COMMIT  // Transaction done in ~5ms

Phase 2: Charge payment (outside transaction)
  result = payment_service.charge(amount, idempotency_key)
  if result.success:
    UPDATE reservations SET status='CONFIRMED'
    Publish booking confirmed event to Kafka
  else:
    // Saga: release inventory, mark reservation failed
    UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1 (for each night)
    UPDATE reservations SET status='PAYMENT_FAILED'

Reservation expiry job (runs every minute):
  SELECT * FROM reservations WHERE status='PENDING_PAYMENT' AND expires_at < NOW()
  For each: release inventory, mark EXPIRED
  
  This catches: payment API call never returned (network died after request was sent),
  or: client crashed without waiting for the payment response.
  
  After 15 minutes, if status is still PENDING_PAYMENT -> auto-release.
```

---

## Failure Scenarios and Degradation

### Failure 1: MySQL Primary goes down

```
What happens:
  All bookings fail (cannot write to primary)
  Search still works from Redis cache + MySQL replica (read-only)
  
Degraded mode:
  Display: "Booking temporarily unavailable, please try again shortly"
  Search: continues normally (from cache)
  
Detection: booking error rate > 5% for 60 seconds -> alert
  
Recovery:
  MySQL Replica promotes to Primary (automatic with MySQL Group Replication or Aurora)
  Promotion time: 30-60 seconds
  Bookings resume
  Missed bookings during outage: cannot be recovered (they didn't happen)
```

### Failure 2: Redis availability cache goes down

```
What happens:
  All search requests miss the cache
  Fall through to MySQL replica for every search request
  MySQL replica: 1,735 reads/sec (manageable if index is properly set up)
  Latency: search latency increases from 5ms to 50-100ms
  
Degraded mode: search works but slower. No errors.
  
Recovery: Redis restarts, cache warms up within 30 seconds (first searches re-populate cache)
```

### Failure 3: Payment service is down

```
What happens:
  Booking transaction completes (inventory decremented, reservation created)
  Payment charge fails
  Reservation stuck in PENDING_PAYMENT status
  
Degraded mode:
  Continue accepting bookings (reservations in PENDING_PAYMENT state)
  Expiry job: 15-minute window before auto-release
  
  If payment service outage > 15 minutes:
    All PENDING_PAYMENT reservations expire and are auto-released
    Users who booked get a notification: "Your booking could not be processed, no charge"
    
Recovery: payment service comes back up, process any pending charges within the 15-minute window
```

### Failure 4: Kafka is down (event pipeline broken)

```
What happens:
  Bookings still succeed (database transaction not affected)
  Confirmation emails are not sent (notification service gets no events)
  Analytics are not updated
  
Degraded mode:
  Core booking functionality works. Non-critical downstream systems delayed.
  
Recovery:
  Kafka recovers, consumers catch up from the committed offset
  Confirmation emails sent (delayed by outage duration)
  Analytics lag by outage duration
```

### Failure 5: Double-booking race condition (database bug)

```
Scenario: a bug causes the WHERE condition to be skipped in the UPDATE statement.
Two bookings both succeed for the last room.

Detection:
  Query: SELECT room_id, date FROM room_inventory WHERE reserved_rooms > total_rooms
  Alert if any row found (reserved > total is impossible in correct operation)
  Run this query every 5 minutes as a canary
  
Remediation:
  Identify the affected reservations (both confirmed for the same room+date)
  Contact one guest: offer refund + upgrade at partner hotel
  Fix the bug + deploy, add test case

Prevention:
  Add a CHECK constraint: ADD CONSTRAINT chk_no_overbooking
    CHECK (reserved_rooms <= total_rooms)
  MySQL will reject any UPDATE that violates this.
  This is the database-level safety net beyond the application-level check.
```

### Blast radius table

```
Component failure   | Blast radius                          | Recovery time
--------------------|---------------------------------------|---------------
MySQL Primary       | All bookings fail; search works       | 30-60s (failover)
MySQL Replica       | Search falls back to primary          | 1-2 min
Redis cache         | Search slower (50ms vs 5ms)           | 30s (warm-up)
Kafka cluster       | Emails delayed; bookings work         | 5-30 min
Payment service     | Bookings pend; auto-expire in 15 min  | Manual: varies
Booking service     | Bookings fail; search works           | 1-2 min (autoscale)
Search service      | Search fails; bookings work           | 1-2 min (autoscale)
```

---

## SSE-Level Brainstorming Questions (Concept-Focused)

### Locking concepts

1. What is the difference between a row lock and a table lock in MySQL? Which does SELECT FOR UPDATE acquire?
2. Optimistic locking assumes conflicts are rare. What metric would you monitor to validate this assumption in production? What threshold would trigger switching to pessimistic?
3. If a transaction holds a row lock (SELECT FOR UPDATE) for 2 seconds, what happens to other transactions waiting for the same row? What is the default lock wait timeout in MySQL?
4. What is a deadlock? Give an example of how it can occur in the hotel booking system and how MySQL detects and resolves it.
5. What is the difference between "phantom reads" and "non-repeatable reads"? Which isolation level prevents each?
6. A booking transaction updates 5 inventory rows (5 nights). In what order should it acquire row locks to prevent deadlocks with another transaction booking overlapping dates?
7. MySQL's default isolation level is REPEATABLE READ. Does this prevent phantom reads? (Hint: MySQL uses gap locks in REPEATABLE READ for this purpose.)
8. Explain the difference between database-level transactions and distributed transactions. Why is distributed transaction (2PC) not used between the booking service and the payment service?

### Inventory design concepts

9. Why store `reserved_rooms` instead of `available_rooms` in the inventory table? What is the risk of storing `available_rooms` as a column?
10. The pre-population job adds 125M rows per day (one day forward). How would you implement this efficiently without locking the table during the operation?
11. What happens to the inventory table when a hotel permanently closes (all rooms should become unavailable)? How do you handle this without deleting 365 rows per room type?
12. A room type is sold out for December 24 but has availability December 23 and 25. A guest searches December 23-25 (2 nights). Which SQL returns the correct result: HAVING COUNT(*) = 2 or HAVING COUNT(*) = 3?
13. What is the "hot row" problem? How does a famous hotel on New Year's Eve exhibit this problem in the inventory table?
14. How would you implement overbooking at the database level? What is the risk of storing total_rooms as physical_rooms * 1.05 (e.g., rounding errors for odd numbers)?

### Idempotency concepts

15. A client generates an idempotency_key UUID before sending the request. What happens if the client crashes before generating the UUID and the user presses "Retry"? (The new attempt will have a new UUID — is this safe? Yes, because the previous request never left the client.)
16. The unique constraint on idempotency_key prevents duplicate inserts. What is the difference between the unique constraint approach and the check-then-insert approach? Which is safer?
17. An idempotency key has a TTL of 24 hours. After 24 hours, the same key can be reused. Is this a problem? (Hint: consider what happens to very old reservations.)
18. A payment provider (Stripe) also accepts idempotency keys. Should you use the same idempotency key for both the booking and the payment charge? What are the risks?
19. How does the Redis lock on the idempotency key (NX PX 30000) handle the case where the booking service crashes while holding the lock? (The lock expires after 30 seconds — the next retry will acquire the lock.)

### Caching concepts

20. The availability cache has 30s TTL. A user searches, sees "available", then is on the booking page for 60 seconds before clicking "Book". The room was booked at second 30 (cache expired, new search would show unavailable). When they click Book at second 60, what happens?
21. Cache invalidation on cancellation: if the cancellation releases inventory for 5 nights, you delete 5 Redis keys. What if the delete fails for 2 of the 5 keys? Are these 2 nights permanently wrong in the cache?
22. A hotel Christmas sale begins at exactly midnight. 100,000 users have the hotel page open. All press "Search" at midnight simultaneously. All get cache misses. How do you prevent 100,000 simultaneous MySQL queries? (Cache stampede.)
23. What is the difference between cache invalidation (DELETE the key) and cache update (SET the new value) after a booking? Which is safer and why?
24. The availability cache uses TTL expiry. An alternative is event-driven invalidation (delete on every booking/cancel). Compare these two approaches.

### Consistency concepts

25. You read availability from the MySQL replica. The replica is 500ms behind the primary. A room was just booked (primary updated, replica not yet). The search shows the room as available. Is this a correctness problem? Why or why not?
26. Strong consistency requires reading from the primary. Eventual consistency allows reading from replicas. For what exact operations in this system is strong consistency required vs. acceptable to use eventual consistency?
27. Two-phase commit (2PC) provides distributed atomicity. Why is the saga pattern (compensating transactions) preferred for the booking + payment flow?
28. What is "read-your-writes" consistency? How does it apply when a user books a room and immediately views "My Reservations"?
29. After a successful booking, the reservation appears in "My Reservations" but the availability search still shows the room as available (cache not yet invalidated). Is this acceptable? How long is acceptable?

### System design extension concepts

30. How would you add multi-region support for this system? A booking in the US must not conflict with a booking from Europe for the same room at the same time.
31. How would you implement a "waitlist" feature: if a room is sold out, the user joins a waitlist and is automatically booked if a cancellation occurs?
32. The hotel wants to offer group bookings (10+ rooms of the same type for the same dates). How does this affect the inventory table design and locking strategy?

---

## Intern to Staff Progression

### Same problem: "Prevent two users from booking the last room simultaneously"

### Intern level

```
Approach: Check-then-act (classic race condition)

function book_room(room_id, date, user_id):
  available = SELECT (total_rooms - reserved_rooms) FROM room_inventory
              WHERE room_id = ? AND date = ?
  
  if available > 0:
    INSERT INTO reservations (room_id, date, user_id) ...
    UPDATE room_inventory SET reserved_rooms = reserved_rooms + 1 ...
    return "Booked!"
  else:
    return "Sold out"

Race condition:
  T=0: User A checks: available = 1 -> passes
  T=0: User B checks: available = 1 -> passes (same value, A hasn't updated yet)
  T=1ms: User A inserts reservation and updates inventory
  T=1ms: User B inserts reservation and updates inventory
  Result: 2 reservations for 1 room. Double booking.
```

### L4 level

```
Approach: Transaction with pessimistic locking (correct but suboptimal)

function book_room(room_id, date, user_id):
  BEGIN TRANSACTION
  
  row = SELECT * FROM room_inventory
        WHERE room_id = ? AND date = ?
        FOR UPDATE  // Lock the row
  
  if (row.total_rooms - row.reserved_rooms) > 0:
    INSERT INTO reservations ...
    UPDATE room_inventory SET reserved_rooms = reserved_rooms + 1 ...
    COMMIT
    return "Booked!"
  else:
    ROLLBACK
    return "Sold out"

Correct: no double booking.
Problem: lock held for entire transaction (including INSERT time).
At 75 bookings/sec, same room: all serialize through this one lock.
Throughput for popular rooms: ~10 bookings/sec (100ms transaction time).
Also: missing idempotency key (double-charge on network retry).
```

### L5 level

```
Approach: Optimistic locking + idempotency key + payment saga

function book_room(room_id, check_in, check_out, user_id, idempotency_key):
  
  // Idempotency check
  existing = SELECT * FROM reservations WHERE idempotency_key = ?
  if existing: return existing
  
  // Acquire Redis lock on idempotency_key
  redis.SET("lock:" + idempotency_key, 1, NX, PX=30000)
  
  BEGIN TRANSACTION
  
  // Optimistic lock: check + decrement is atomic
  for each night in [check_in, check_out):
    rows = UPDATE room_inventory
           SET reserved_rooms = reserved_rooms + 1
           WHERE room_id = ? AND date = ? AND (total_rooms - reserved_rooms) > 0
    if rows == 0:
      ROLLBACK
      return "Room not available"
  
  INSERT INTO reservations (status='PENDING_PAYMENT', idempotency_key, ...)
  COMMIT
  
  // Payment outside transaction
  result = payment_service.charge(amount, idempotency_key)
  if result.success:
    UPDATE reservations SET status='CONFIRMED'
    publish_to_kafka("booking_confirmed", ...)
  else:
    // Saga: rollback inventory
    release_inventory(room_id, check_in, check_out)
    UPDATE reservations SET status='PAYMENT_FAILED'
```

### L6 level

```
Additional concerns L6 raises:
  1. Sharding: hotels are sharded by hotel_id. Famous hotels on one shard
     -> hot shard problem. Proposes: consistent hashing with virtual nodes,
     or dedicated shards for top-100 hotels by booking volume.

  2. Overbooking: total_rooms in inventory is physical_rooms * 1.05.
     ML model predicts cancellation rate per hotel per date window.
     Overbooking rate adjusts dynamically. Alert when gap between bookings
     and physical rooms exceeds the predicted cancellation count.

  3. Multi-region: guest in Tokyo books room in NYC. Booking must go to
     the US region (where the hotel's inventory shard lives). Geo-routing
     at the API gateway layer. No cross-region distributed transactions.

  4. Reservation hold: instead of immediately decrementing inventory,
     place a "soft hold" that expires in 15 minutes. While in soft hold,
     room shows as "unavailable" in search (pessimistic for user-facing view)
     but inventory is not permanently decremented until payment is confirmed.
     Reduces saga complexity: no compensating transaction if payment fails
     (soft hold expires, inventory auto-released).

  5. Monitoring: per-hotel booking success rate. If hotel X has 50% booking
     failures (all returning "sold out"), is it actually sold out or is
     there a lock contention bug? Track retry rate per hotel.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)             | L6 (Staff)                     |
+---------------------+----------------------------+--------------------------------+
| Double-booking      | Optimistic locking with     | Hybrid: optimistic normally,  |
| prevention          | UPDATE condition check      | pessimistic for last room.    |
|                     |                             | Per-hotel booking queue for   |
|                     |                             | flash sales.                  |
+---------------------+----------------------------+--------------------------------+
| Inventory model     | Pre-populated table,        | Dynamic overbooking rate per  |
|                     | static total_rooms          | hotel based on ML-predicted   |
|                     |                             | cancellation probability.     |
+---------------------+----------------------------+--------------------------------+
| Idempotency         | Client-generated UUID +     | Full idempotency chain:       |
|                     | DB unique constraint        | booking key == payment key,   |
|                     |                             | idempotency TTL policy,       |
|                     |                             | audit log for forensics.      |
+---------------------+----------------------------+--------------------------------+
| Payment failure     | Saga: compensating          | Reservation hold (soft lock)  |
|                     | transaction to release      | + time-bound expiry.          |
|                     | inventory                   | Proactive retries with ML     |
|                     |                             | model for payment retry.      |
+---------------------+----------------------------+--------------------------------+
| Sharding            | Shard by hotel_id,          | Consistent hashing, hot hotel |
|                     | acknowledge hot shard risk  | detection + dedicated shards, |
|                     |                             | live shard rebalancing.       |
+---------------------+----------------------------+--------------------------------+
| Caching             | 30s TTL, invalidate on      | Multi-layer cache: CDN for    |
|                     | book/cancel                 | hotel static data, Redis for  |
|                     |                             | availability, stampede        |
|                     |                             | prevention (probabilistic     |
|                     |                             | early expiration).            |
+---------------------+----------------------------+--------------------------------+
| Consistency         | Strong for bookings,        | Explicitly quantifies the     |
|                     | eventual for search         | cost of each model, knows     |
|                     | (accepted trade-off)        | which operations are MUST-    |
|                     |                             | READ-PRIMARY vs replica-ok.   |
+---------------------+----------------------------+--------------------------------+
| Multi-region        | Out of scope (single DC)    | Geo-routing to hotel's region,|
|                     |                             | no cross-DC booking txn,      |
|                     |                             | conflict-free by design.      |
+---------------------+----------------------------+--------------------------------+
| Overbooking         | Static 5% overbooking rate  | Dynamic rate: ML model per    |
|                     | acknowledged                | hotel + date + booking window.|
|                     |                             | Walk policy with cost model.  |
+---------------------+----------------------------+--------------------------------+
| Monitoring          | Error rate, latency,        | Per-hotel booking success     |
|                     | double-booking alerts       | rate, retry rate, lock        |
|                     |                             | contention per room, revenue  |
|                     |                             | impact per incident.          |
+---------------------+----------------------------+--------------------------------+
| Failure articulation| Describes failure modes      | Quantifies blast radius:      |
|                     | when asked                  | "Primary down = 0 bookings    |
|                     |                             | for 60s = 75 lost bookings =  |
|                     |                             | ~$11K lost revenue at avg     |
|                     |                             | $150/room-night."             |
+---------------------+----------------------------+--------------------------------+
| Architecture        | Correct, clear design       | Proactively asks: "What is    |
| communication       |                             | the hotel's SLA for walked    |
|                     |                             | guests? That determines our   |
|                     |                             | uptime requirement."          |
+---------------------+----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Booking.com Double-Booking During Black Friday Sale (2018)

**Company:** Booking.com  
**What happened:** During a flash sale, a popular beachfront property in Bali released 10 rooms at a heavily discounted price at exactly midnight. Within 30 seconds, all 10 rooms were overbooked — 47 confirmed bookings existed for 10 rooms. The root cause was a race condition in the inventory check: the application read available count from a Redis cache, found "7 available", and then issued separate UPDATE statements to both the cache and the database. The Redis update and database update were not atomic. Under high concurrency, multiple requests read the same "7 available" from Redis before any wrote back "6 available".

**Root cause:** Availability check in cache and inventory decrement in database were two separate operations. The system trusted the cache for the availability check rather than the database UPDATE's `rows_affected`.

**ASCII diagram:**

```
T=0: Redis: avail=7
T=0: Request A reads Redis: 7 available -> proceed
T=0: Request B reads Redis: 7 available -> proceed
T=0: Request C reads Redis: 7 available -> proceed
...47 requests all read "7 available" before any writes back

T=1ms: Request A writes: Redis SET avail=6, DB UPDATE reserved=reserved+1
T=1ms: Request B writes: Redis SET avail=6, DB UPDATE reserved=reserved+1
...47 DB UPDATEs succeed (no WHERE condition checking capacity)
Result: reserved_rooms = 47, total_rooms = 10. 37 extra bookings.
```

**Fix:** The authoritative availability check must be the database UPDATE's `rows_affected`, not a pre-check from cache. The pre-check from cache is a fast-reject optimization only; the UPDATE must include the `WHERE (total - reserved) > 0` condition and check that exactly 1 row was affected.

**Staff lesson:** Never use a cached value as the authoritative gate for a reservation. Cache is for read optimization. The database transaction with a conditional UPDATE is the gate. If the cache says "available" but the DB says "0 rows affected" — the DB wins, always.

---

### Incident 2: Airbnb Duplicate Charge Bug During App Relaunch (2017)

**Company:** Airbnb  
**What happened:** Airbnb relaunched their mobile app. The new app had a retry mechanism for failed HTTP requests, but the retry always generated a new booking request (without an idempotency key). When a booking request timed out (due to high server load from the relaunch), the app automatically retried. Users were charged twice for the same booking. Some users reported charges 3 or 4 times. The incident affected ~2,000 users and required a manual refund campaign.

**Root cause:** No idempotency key implementation. Each booking request was treated as a new independent booking even if it was a retry of a failed one.

**Fix:** 
- Client generates a UUID (idempotency key) when the user first initiates a booking
- The same key is sent on all retries for the same booking attempt
- Server checks for existing bookings with that key before processing
- Unique constraint on idempotency_key column prevents duplicate inserts

**Staff lesson:** Any operation that involves money must be idempotent from end to end. The idempotency key must be generated before any network call is made, not after. "Generate new key on retry" is always wrong for financial operations.

---

### Incident 3: Hotels.com Availability Cache Staleness During New Year's Eve (2020)

**Company:** Hotels.com  
**What happened:** For New Year's Eve 2020-2021, Hotels.com had set their availability cache TTL to 300 seconds (5 minutes) for performance reasons. During the high-traffic period, a popular downtown Chicago hotel sold its last room. The cache still showed "2 rooms available" for the next 5 minutes. During those 5 minutes, 1,400 users attempted to book. All 1,400 saw "available" and proceeded to the booking page. When they submitted the booking, they all received errors. The customer service team was overwhelmed.

**Root cause:** Cache TTL was too long. Cache invalidation on booking was disabled during the high-traffic period (a performance optimization that backfired).

**Fix:**
- Reduce TTL to 30 seconds during known high-traffic events
- Re-enable cache invalidation on booking (it was erroneously disabled)
- Add proactive cache warm-up: pre-populate cache for high-demand hotels before midnight
- Show "limited availability" UI message when available_count <= 2 (more urgent refresh)

**Staff lesson:** Cache invalidation being "disabled for performance" is usually a sign that the cache design is wrong, not that invalidation is the problem. The right fix is reducing TTL and ensuring invalidation is always on, not faster reads at the cost of correctness.

---

### Incident 4: Expedia Inventory Pre-Population Failure (New Year 2022)

**Company:** Expedia  
**What happened:** Expedia's nightly job that pre-populates the inventory table for future dates failed silently on December 28, 2021. The job was supposed to create rows for January 1-3, 2022. It did not. When users searched for hotels on January 1-3, the availability queries returned 0 results (no rows in the inventory table = no available rooms). For 6 hours on December 29-30, Expedia showed "no hotels available" for all of January 1-3. Customers went to competitors. Revenue loss estimated at $8M for those 6 hours.

**Root cause:** The nightly job had a date calculation bug. It was supposed to add 3 days forward from "today." A timezone conversion error (UTC vs local time) caused the job to calculate dates correctly but skip December 28-30 (already past) and start at January 4.

**Fix:**
- Add monitoring: alert if inventory table has 0 rows for any future date where bookings exist
- Add canary check after nightly job: verify that rows for D+1, D+2, D+3 exist for top 1,000 hotels
- Fix the timezone bug in the date calculation

**Staff lesson:** Silent failure of a data population job is worse than a loud crash. A crashed job pages the on-call engineer immediately. A silently succeeded-but-wrong job may not be detected for hours. Add explicit validation after every batch job that checks the expected state was achieved.

---

### Incident 5: Marriott Multi-Room Booking Deadlock (2019)

**Company:** Marriott (via their reservation platform)  
**What happened:** Marriott allowed corporate clients to book multiple room types simultaneously (e.g., 5 deluxe rooms + 3 suite rooms for a conference). The booking flow acquired row locks in this order: deluxe first, then suite. A concurrent individual booking for the same hotel acquired locks in the order: suite first, then deluxe. Under high load, these two bookings deadlocked: Booking A held the deluxe lock and waited for the suite lock. Booking B held the suite lock and waited for the deluxe lock. MySQL detected the deadlock after 50 seconds and killed one transaction. The killed transaction retried, encountered the same deadlock again. Some bookings took 5-10 minutes to complete or were abandoned.

**Root cause:** Two transaction types acquired the same row locks in different orders. Classic deadlock pattern.

**ASCII diagram:**

```
Corporate booking:     Individual booking:
Lock deluxe (SUCCESS)  Lock suite (SUCCESS)
Wait for suite...      Wait for deluxe...
[DEADLOCK]             [DEADLOCK]

MySQL detects cycle -> kills one transaction (random)
```

**Fix:** Always acquire row locks in the same canonical order across all transactions. Order: sort by (room_id, date) ascending before issuing any SELECT FOR UPDATE or UPDATE statements. This ensures all transactions acquire locks in the same sequence, eliminating deadlock cycles.

**Staff lesson:** Deadlocks are not random. They have a specific pattern: circular lock dependencies. The solution is always to canonicalize the lock acquisition order. Every transaction that touches multiple rows must acquire them in the same global order (e.g., sorted by primary key).

---

## Exercises

### Exercise 1: Room Inventory Schema

**Problem:** Design the SQL schema for the room_inventory table. Include the primary key, the constraint that prevents reserved_rooms from exceeding total_rooms, and the index needed for efficient availability queries.

**Solution:**

```
CREATE TABLE room_inventory (
    room_id      BIGINT NOT NULL,
    date         DATE   NOT NULL,
    total_rooms  SMALLINT NOT NULL DEFAULT 1,
    reserved_rooms SMALLINT NOT NULL DEFAULT 0,
    
    PRIMARY KEY (room_id, date),
    
    CONSTRAINT chk_reserved_lte_total
        CHECK (reserved_rooms >= 0 AND reserved_rooms <= total_rooms),
    
    CONSTRAINT chk_total_positive
        CHECK (total_rooms > 0)
);

-- The PRIMARY KEY (room_id, date) IS the index for availability queries.
-- SELECT ... WHERE room_id = ? AND date BETWEEN ? AND ? uses this index.
-- No additional index needed for single-room availability lookups.

-- For hotel-level availability search (all rooms in a hotel):
-- Need: hotel_id -> room_id mapping (in the rooms table, not here)
-- JOIN rooms ON room_inventory.room_id = rooms.room_id WHERE rooms.hotel_id = ?
-- Index needed: CREATE INDEX idx_rooms_hotel ON rooms(hotel_id)

Notes:
  - reserved_rooms <= total_rooms enforced at DB level (safety net)
  - CHECK constraint: MySQL 8.0+ enforces CHECK constraints
  - For older MySQL: enforce via application logic + triggers
```

---

### Exercise 2: Optimistic Locking SQL

**Problem:** Write the SQL UPDATE statement that atomically checks availability and decrements inventory in one operation. Explain why 0 rows affected means the room is sold out.

**Solution:**

```
-- For a single night booking:
UPDATE room_inventory
SET reserved_rooms = reserved_rooms + 1
WHERE room_id = 123
AND date = '2024-12-24'
AND (total_rooms - reserved_rooms) > 0;

-- Check: affected_rows = result.rowcount

-- If affected_rows == 1: Success. Room was available, now reserved.
-- If affected_rows == 0: Failure. Room was not available when the UPDATE ran.

-- Why 0 rows affected means sold out:
-- MySQL evaluates the WHERE clause before executing the SET.
-- The WHERE condition is checked with a row-level lock held.
-- If (total_rooms - reserved_rooms) > 0 is FALSE when the lock is held,
-- the UPDATE affects 0 rows and releases the lock immediately.
-- No other transaction can change reserved_rooms between the WHERE check and the SET.
-- Therefore: 0 rows affected = definitively not available at the time of this statement.

-- For a multi-night booking (3 nights: Dec 24, 25, 26):
-- Issue 3 separate UPDATEs in a transaction. If any returns 0 rows: ROLLBACK all 3.

BEGIN TRANSACTION;

UPDATE room_inventory SET reserved_rooms = reserved_rooms + 1
WHERE room_id = 123 AND date = '2024-12-24' AND (total_rooms - reserved_rooms) > 0;
-- If rows_affected == 0: ROLLBACK; return "not available for Dec 24"

UPDATE room_inventory SET reserved_rooms = reserved_rooms + 1
WHERE room_id = 123 AND date = '2024-12-25' AND (total_rooms - reserved_rooms) > 0;
-- If rows_affected == 0: ROLLBACK; return "not available for Dec 25"

UPDATE room_inventory SET reserved_rooms = reserved_rooms + 1
WHERE room_id = 123 AND date = '2024-12-26' AND (total_rooms - reserved_rooms) > 0;
-- If rows_affected == 0: ROLLBACK; return "not available for Dec 26"

INSERT INTO reservations (...) VALUES (...);

COMMIT;
```

---

### Exercise 3: Idempotency Key Flow

**Problem:** A user books a room. The server processes the request (books the room, charges the card), but the response is lost in the network. The user sees a loading spinner and clicks "Retry" after 10 seconds. Describe the exact sequence of events on the second request.

**Solution:**

```
First request (T=0):
  Client generates idempotency_key = "uuid-abc123" (generated once, before any request)
  POST /bookings {room_id: 42, check_in: "2024-12-24", ..., idempotency_key: "uuid-abc123"}
  Server receives, processes, commits reservation_id = 9999, status = CONFIRMED
  Server sends response... network drops it.
  Client never receives response. Spinner shows.

Second request (T=10s):
  Client sends: POST /bookings {same params, idempotency_key: "uuid-abc123"}

Server receives second request:
  Step 1: SELECT * FROM reservations WHERE idempotency_key = 'uuid-abc123'
          Returns: {reservation_id: 9999, status: 'CONFIRMED', room_id: 42, ...}
  Step 2: Return existing reservation immediately.
          HTTP 200 OK {reservation_id: 9999, status: 'CONFIRMED', ...}
  Step 3: NO inventory change. NO payment charge. NO new reservation.

Client receives: 200 OK with reservation 9999. Shows "Booking confirmed."

What the user sees:
  First request: spinner
  Second request (retry): "Booking confirmed" immediately
  They were booked once, charged once. The retry was a no-op.

Key: the idempotency_key "uuid-abc123" was the same on both requests.
     The server recognized the second as a retry and returned the first's result.
```

---

### Exercise 4: Storage Calculation for Pre-Populated Inventory

**Problem:** Calculate the total storage needed for the room_inventory table. Assumptions: 500K hotels, 5 room types per hotel, 365 days pre-populated. Show your work.

**Solution:**

```
Step 1: Total rows
  500,000 hotels
  * 5 room types per hotel = 2,500,000 total room types
  * 365 days per room type = 912,500,000 rows (round to 912M)

Step 2: Row size
  room_id:        BIGINT = 8 bytes
  date:           DATE   = 3 bytes (MySQL DATE is stored in 3 bytes)
  total_rooms:    SMALLINT = 2 bytes
  reserved_rooms: SMALLINT = 2 bytes
  Row data:       15 bytes
  Row overhead (MySQL InnoDB per-row overhead): ~7 bytes
  Effective row size: ~22 bytes

Step 3: Raw data size
  912M rows * 22 bytes = 20 GB

Step 4: Primary key index (B-tree on room_id, date)
  Index entry: room_id (8) + date (3) + row pointer (6) = 17 bytes
  Leaf nodes: 912M * 17 = 15.5 GB
  Internal nodes: ~10% of leaf = 1.5 GB
  Total index: ~17 GB

Step 5: InnoDB overhead (metadata, undo logs, buffer pool)
  ~15% overhead: 37 GB * 0.15 = 5.5 GB

Total: 20 + 17 + 5.5 = ~42 GB

With 8 shards: 42 GB / 8 = 5.25 GB per shard

This is very manageable. A single modern MySQL server handles 500 GB+ comfortably.
At 5.25 GB per shard, each shard has 100x headroom for additional data (indexes, caching).
```

---

### Exercise 5: Cache Invalidation Strategy

**Problem:** A user books room_id=42 for Dec 24, 25, 26. Design the exact Redis cache operations that must happen after the booking succeeds.

**Solution:**

```
After booking succeeds (transaction committed):

Step 1: Identify affected cache keys
  For each night in [check_in, check_out):
    key = "avail:42:2024-12-24"
    key = "avail:42:2024-12-25"
    key = "avail:42:2024-12-26"

Step 2: Invalidate (DELETE) these keys
  Option A: Simple DELETE (recommended)
    redis.DEL("avail:42:2024-12-24")
    redis.DEL("avail:42:2024-12-25")
    redis.DEL("avail:42:2024-12-26")
    
    Why DELETE not UPDATE:
    - DELETE is safe: next read will miss cache, go to DB, get correct value
    - UPDATE with cached_val - 1 is risky: if cache was already stale,
      we write stale_val - 1 (wrong)
    - Also: if booking failed (rolled back), DELETE is a no-op
      (next read re-populates from DB). UPDATE with -1 on rollback would
      show wrong count (artificially low).

  Option B: Use pipeline for efficiency
    pipeline = redis.pipeline()
    pipeline.delete("avail:42:2024-12-24")
    pipeline.delete("avail:42:2024-12-25")
    pipeline.delete("avail:42:2024-12-26")
    pipeline.execute()
    // One round trip for all 3 deletes

Step 3: Handle cache invalidation failure
  If Redis DELETE fails (Redis down):
    Do NOT fail the booking. The booking already succeeded in MySQL.
    The stale cache will self-correct when its 30s TTL expires.
    Log the failure. Alert if Redis is consistently down.
    
    The 30-second TTL is the safety net: even if invalidation fails,
    stale availability data expires within 30 seconds.
    Next search after 30s will miss cache, go to DB, get correct value.
```

---

### Exercise 6: Trace a Payment Failure

**Problem:** A user books a room. The database transaction succeeds (room reserved). Then the payment service call times out. Trace the exact sequence of events from the perspective of the booking service. What state is the system left in? What cleans it up?

**Solution:**

```
T=0: Client sends booking request
  idempotency_key = "uuid-xyz789"

T=0 to T=50ms: Booking Service processes
  Idempotency check: no existing reservation. Proceed.
  Acquire Redis lock on "idemplock:uuid-xyz789"
  BEGIN TRANSACTION
  3x UPDATE room_inventory (3 nights, Dec 24-26): all succeed (rows_affected=1)
  INSERT INTO reservations (reservation_id=5555, status='PENDING_PAYMENT',
    expires_at=NOW()+15min, idempotency_key='uuid-xyz789')
  COMMIT
  // At this point: room is reserved, payment not yet attempted

T=50ms: Call payment service
  POST /payments {amount: $450, idempotency_key: "uuid-xyz789"}
  ...waiting...
  ...waiting...

T=5050ms (5 seconds): Payment service timeout
  No response received. Network timeout.

T=5050ms: Booking Service handles failure
  Result = PAYMENT_TIMEOUT
  
  // Saga: release inventory
  BEGIN TRANSACTION
  UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1
    WHERE room_id = 42 AND date = '2024-12-24'
  UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1
    WHERE room_id = 42 AND date = '2024-12-25'
  UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1
    WHERE room_id = 42 AND date = '2024-12-26'
  UPDATE reservations SET status = 'PAYMENT_FAILED'
    WHERE reservation_id = 5555
  COMMIT
  
  // Add to retry table for payment retry attempt
  INSERT INTO pending_payments (reservation_id=5555, next_retry_at=NOW()+60s)
  
  // Invalidate cache (room is available again)
  redis.DEL("avail:42:2024-12-24", "avail:42:2024-12-25", "avail:42:2024-12-26")
  
  // Release Redis lock
  redis.DEL("idemplock:uuid-xyz789")

T=5050ms: Return to client
  HTTP 402 Payment Required
  {error: "Payment could not be processed", reservation_id: 5555}

Final state:
  - reserved_rooms is back to original (saga completed)
  - Reservation status = 'PAYMENT_FAILED'
  - Room shows as available in next search (cache invalidated)
  - Pending payment retry entry exists (retry worker will attempt payment again)

T+60s: Retry worker attempts payment again
  If payment was actually charged (timeout ≠ not charged):
    Payment provider returns idempotent response (same amount already charged)
    Update reservation status = 'CONFIRMED'
    Email confirmation sent
  If payment was truly not charged:
    Retry charges the card
    If success: update status = 'CONFIRMED'
    If failure: mark PAYMENT_FAILED permanently, notify user

Edge case: saga fails too
  What if the inventory release UPDATE fails?
  The reservation status is PENDING_PAYMENT with an expires_at.
  The expiry job (runs every minute) will find this reservation at expires_at:
    Force release inventory: UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1
    Mark reservation EXPIRED
  Maximum time room is stuck reserved: 15 minutes (the expiry TTL).
```

---

## Homework

### Short homework

**Short 1:** Take any hotel booking website (Booking.com, Expedia, Hotels.com). Find a popular hotel near a major holiday. Observe: does the website show exact available room count or just "limited availability"? Does the count update in real-time as you watch? What does this tell you about their consistency model for availability search?

**Short 2:** Implement a simple optimistic locking example in any SQL database (SQLite is fine):
- Create a table: `items (id, name, stock INTEGER, version INTEGER)`
- Insert one item with stock=5, version=0
- Write two concurrent transactions that each try to decrement stock by 1
- Use optimistic locking: `UPDATE items SET stock=stock-1, version=version+1 WHERE id=? AND version=?`
- Observe that one transaction succeeds (rows_affected=1) and one fails (rows_affected=0)

**Short 3:** Look up the "lost update" problem in database concurrency. How is it different from the double-booking race condition? Which isolation level in MySQL prevents lost updates? Run an experiment with two database connections at READ COMMITTED isolation level vs REPEATABLE READ to observe the difference.

### Deep homework

**Deep 1:** Build a mini hotel reservation system in Python or Go:
- Use SQLite for the database
- Tables: rooms (room_id, total_rooms), inventory (room_id, date, reserved_rooms), reservations (id, room_id, check_in, check_out, idempotency_key)
- Implement: book_room(room_id, check_in, check_out, idempotency_key) with optimistic locking
- Test: spin up 50 concurrent threads, all trying to book the last room for the same date
- Measure: how many succeed (should be exactly 1), how many fail cleanly, any double-bookings?
- Add idempotency: run each booking twice with the same key, confirm exactly one booking exists

**Deep 2:** Design the "waitlist" feature:
- When a room is sold out, a user can join the waitlist for that room+date combination
- When a cancellation occurs, the first user on the waitlist is automatically booked
- Design the data model, the event flow (cancellation triggers booking), and the failure handling (what if the waitlisted user's payment fails?)
- Consider: race conditions in the waitlist (two cancellations happen simultaneously, only one waitlist user should be booked)

**Deep 3:** Read Airbnb's engineering blog post about their database consistency challenges (search: "Airbnb technical blog database availability"). Identify: what consistency model did they choose for listing availability? How do they handle the race condition between viewing availability and booking? Compare their approach to the design in this chapter. Write 500 words.

---

## Glossary

**Optimistic locking:** A concurrency control strategy where no lock is acquired before reading. Instead, the write operation includes a condition that validates the data has not changed since the read. If the condition fails (another writer won the race), the write returns 0 rows affected and the caller retries or returns an error.

**Pessimistic locking:** A concurrency control strategy where an exclusive lock is acquired before reading the data, preventing any other transaction from modifying the locked rows until the lock is released. In SQL: `SELECT ... FOR UPDATE`.

**Idempotency key:** A client-generated unique identifier sent with every request. The server uses it to detect retries of the same operation and return the same result without re-executing the operation. Prevents duplicate charges and double-bookings on network retry.

**Room inventory table:** A pre-populated table storing available room count per room per date. Enables O(1) atomic availability check and reservation in a single UPDATE statement.

**Double-booking:** A correctness failure where two reservations exist for the same room on the same date, but only one physical room is available. Occurs when two concurrent booking requests both see "available" before either updates the inventory.

**Saga pattern:** A design pattern for managing distributed transactions across multiple services. Each step in the saga has a corresponding compensating transaction that undoes it. If a step fails, all previous steps are compensated. Used when 2-phase commit is not available (e.g., external payment providers).

**Compensating transaction:** A transaction that reverses the effect of a previous transaction. In hotel booking: if payment fails after inventory was decremented, a compensating transaction increments inventory back.

**Reservation expiry:** An automatic mechanism that cancels reservations stuck in PENDING_PAYMENT status after a timeout (e.g., 15 minutes). Prevents rooms from being held indefinitely by abandoned booking attempts.

**Overbooking:** Intentionally selling more reservations than physical rooms exist, because historical data shows a percentage of guests cancel. If all guests show up, some are "walked" (sent to another hotel at the hotel's expense).

**Walking a guest:** The practice of sending a guest who has a confirmed reservation to a different hotel when the original hotel is at full occupancy (due to overbooking or maintenance). The original hotel covers the costs.

**Cache invalidation:** Deleting or updating cached values when the underlying data changes. In hotel booking: deleting the cached available_count when a room is booked or cancelled.

**Sharding by hotel_id:** Distributing the room_inventory table across multiple database nodes, where all rows for a given hotel are on the same node. Ensures single-node transactions for all bookings at one hotel.

**Hot shard:** A database shard that receives disproportionately more traffic than other shards. In hotel booking: a shard hosting famous or popular hotels during peak travel periods.

**Pre-population job:** A scheduled batch process that creates future rows in the room_inventory table. Runs nightly to add one day forward (up to 365 days ahead), ensuring availability can always be checked for future dates.

**Reservation hold (soft lock):** An intermediate reservation state (PENDING_PAYMENT) where inventory is decremented but the booking is not confirmed until payment succeeds. If payment does not arrive within the hold window, inventory is automatically released.

---

## The One-Sentence Summary

> "Hotel reservation = pre-populated room_inventory table (room_id x date x count) enabling a single atomic UPDATE (WHERE total - reserved > 0) to both check and decrement availability, making 0 rows affected the double-booking signal, combined with a client-generated idempotency key (unique DB constraint) for retry safety, plus a saga pattern (inventory decrement + payment + compensating rollback on failure) — the core insight is that the availability check and the reservation must be a single atomic database operation, not two separate steps."

---

## Interview Q&A — Most Common Cross-Questions

These are the follow-up questions interviewers ask immediately after your design. Each answer is meant to be said out loud in under 60 seconds.

---

**Q1: How do you prevent double-booking? Show me the exact mechanism.**

Two users simultaneously check availability — both see "1 room available." Both attempt to book. The race happens between the read and the write.

The fix: merge the check and the write into one SQL statement. The UPDATE itself contains the availability condition:

```
UPDATE room_inventory
SET reserved_rooms = reserved_rooms + 1
WHERE room_id = ? AND date = ?
AND (total_rooms - reserved_rooms) > 0
```

MySQL holds a row-level lock for the duration of this statement. Two concurrent UPDATEs for the same row serialize at the database level. The first succeeds — returns 1 row affected. The second now sees `reserved_rooms = total_rooms`, condition fails, returns 0 rows affected. Zero rows affected = sold out = ROLLBACK. One winner, one clean rejection, no double-booking.

---

**Q2: What is the difference between optimistic and pessimistic locking? When do you use each?**

**Optimistic:** No lock acquired upfront. The UPDATE contains a condition that fails if someone else already took the last room. High throughput — concurrent bookings for different rooms do not block each other. Retry overhead only when contention is high.

**Pessimistic:** `SELECT ... FOR UPDATE` acquires an exclusive row lock before reading. Other transactions wanting the same row wait. One winner, no retries. Lock held for the full transaction duration — slow if many concurrent requests queue up.

**Rule:** Use optimistic by default. Switch to pessimistic (`SELECT FOR UPDATE`) when `available_rooms <= 1`. That is the highest-contention case. With pessimistic locking the last room has exactly one clean winner instead of a retry storm.

---

**Q3: Two users try to book the last room at the exact same millisecond. Walk me through step by step.**

Both issue the same UPDATE simultaneously. MySQL serializes row-level writes internally. User A's UPDATE runs first: condition passes (available = 1), `reserved_rooms` becomes 1, returns 1 row affected. User A proceeds to INSERT reservation and COMMIT.

User B's UPDATE runs next: `total_rooms - reserved_rooms = 1 - 1 = 0`, condition fails, returns 0 rows affected. Booking service sees 0 rows → ROLLBACK → returns 409 "Room no longer available."

Result: one booking, one clean rejection, no data anomaly.

---

**Q4: Why pre-populate the room_inventory table instead of computing availability from the reservations table?**

**Performance:** Computing from reservations means scanning all confirmed bookings for a room on a given date. For a popular hotel that is thousands of rows per scan. At 100K searches/sec the database melts. Pre-populated table: single-row primary-key lookup on `(room_id, date)`, O(1), sub-millisecond.

**Atomicity:** To atomically check-and-decrement, you need a single row to UPDATE. With the reservations table you would COUNT (a scan), check against total, then INSERT — three steps that cannot be made truly atomic without locking the entire scan result.

Storage: 912M rows × 16 bytes = 14.6 GB across a sharded cluster. Trivial.

---

**Q5: What is an idempotency key? What exact problem does it solve?**

The problem: user clicks Book. Network times out. Client retries. Without idempotency: two booking requests arrive, two reservations are created, the guest is charged twice.

The idempotency key is a UUID the client generates **once before any request**. The same key is sent on every retry. The server checks first: if a reservation already exists with this key, return it without processing again. If not, process and store the reservation with this key. The `UNIQUE INDEX (idempotency_key)` in the reservations table is the database-level safety net — even if two requests race past the application check, only one INSERT can succeed.

Three scenarios it covers: (1) network drop before server receives request — retry is treated as first attempt, safe; (2) server commits reservation then crashes before responding — retry finds existing reservation; (3) response lost in network — retry finds existing reservation. In all cases: exactly one booking, exactly one charge.

---

**Q6: What happens if the payment service fails after the room is reserved?**

The booking is two-phase: Phase 1 commits the DB transaction (inventory decremented, reservation in `PENDING_PAYMENT`). Phase 2 calls the payment service outside the transaction.

If payment fails: the room is reserved but not paid for. We run a **compensating transaction**: increment `reserved_rooms` back, set reservation status to `PAYMENT_FAILED`. This is the Saga pattern — each step has a compensating step that undoes it.

If we cannot determine whether the charge happened (payment timeout): do not immediately compensate. Add to a retry queue. The retry worker calls payment again with the same idempotency key — the payment provider's idempotent response tells us if it was already charged.

Backstop: every `PENDING_PAYMENT` reservation has `expires_at = NOW() + 15 minutes`. A job running every minute auto-cancels expired reservations and releases inventory.

---

**Q7: Your availability cache has 30s TTL. A room gets booked. For 30 seconds the search still shows it available. A user sees it, tries to book, fails. Is this acceptable?**

Yes, by design. The system has two tiers: availability search (Redis cache, eventual consistency) and booking (database, strong consistency). The cache is a fast-reject optimization, not the source of truth.

The worst case UX: user sees "available," clicks Book, gets "This room was just taken." This is the standard e-commerce pattern — every major booking site works this way.

The alternative — strong consistency for search — means hitting the database for every search. At peak that is 8,000+ DB reads/sec on top of booking load. p99 search latency: 500ms instead of 5ms. Not worth it. Correctness is enforced at booking time.

---

**Q8: What if the user's client retries the booking request while the first request is still in-flight?**

Two requests with the same idempotency key arrive simultaneously. The Redis lock handles this: before processing, acquire `SET lock:{idempotency_key} 1 NX PX 30000`. The second request sees the lock exists, returns 409 "Request in progress." The client retries after 30 seconds (lock TTL expires). By then the first request has completed. The idempotency check finds the existing reservation and returns it.

If Redis is down when both arrive: both reach the database INSERT. The `UNIQUE constraint` on `idempotency_key` means only one INSERT succeeds. The other gets a Duplicate Key error → SELECT existing reservation → return it. One booking regardless.

---

**Q9: How would you shard the room_inventory table? What is the hot shard problem?**

Shard by `hotel_id`. A booking for hotel H only touches `room_inventory` rows for that hotel's rooms. Sharding by `hotel_id` ensures all inventory for one hotel lives on one shard → single-shard transaction → no distributed coordination.

Not by `room_id` (a multi-night booking spans multiple rooms of the same hotel → cross-shard). Not by `date` (a multi-night booking spans multiple dates → cross-shard).

**Hot shard:** Famous hotels (Marriott NYC on New Year's Eve) get 100× average traffic. All their inventory is on one shard. That shard becomes the bottleneck.

Detection: monitor writes/sec per shard, alert if any shard > 3× average.

Fix: dedicated shard for top-100 hotels by booking volume, or a per-hotel serializing queue (Kafka topic partitioned by hotel_id). The queue consumer processes one booking at a time per hotel — eliminates all lock contention on the hot shard.

---

**Q10: What is the saga pattern? Why not use a distributed transaction?**

A saga is a sequence of local transactions each with a compensating transaction. If step N fails, run compensating transactions for all previous steps in reverse.

Hotel booking saga: (1) Decrement inventory, (2) Charge payment, (3) Confirm reservation. If step 2 fails: run compensating step 1 (increment inventory back), set reservation to PAYMENT_FAILED.

Why not 2PC (two-phase commit): 2PC requires all participants to implement the 2PC protocol. The payment service (Stripe/Braintree) is an external SaaS — it does not participate in our 2PC. Sagas work across service boundaries via compensating transactions and do not hold locks across external APIs. 2PC holding locks while waiting for a slow external payment API call is dangerous — lock timeouts, cascading failures.

---

**Q11: How do you handle cancellation atomically — both marking cancelled AND releasing inventory?**

Both in a single MySQL transaction:

```
START TRANSACTION
  UPDATE reservations SET status = 'CANCELLED' WHERE reservation_id = ?
  UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1
    WHERE room_id = ? AND date = ?   -- one UPDATE per night
COMMIT
```

Either both commit or both rollback. There is no window where the reservation is cancelled but inventory still shows reserved. ACID atomicity handles this.

The refund (calling payment service) happens outside the transaction following the saga pattern. If the refund fails, the cancellation and inventory release are still correct. The refund is retried separately via a `pending_refunds` table and retry worker.

---

**Q12: What happens if your booking service crashes mid-transaction?**

MySQL automatically rolls back uncommitted transactions on crash recovery. The `reserved_rooms` decrement was part of a transaction that never committed. MySQL replays its WAL and undoes the incomplete transaction. Inventory is restored.

The client sees a connection timeout or 500. The client retries with the same idempotency key. The server finds no existing reservation (the transaction rolled back), processes normally — exactly one booking.

This is different from crashing after COMMIT but before sending the response. In that case the reservation IS durable. The retry finds the existing reservation via idempotency key and returns it. Either way: exactly one booking.

---

**Q13: Why MySQL over NoSQL for the booking transaction?**

Bookings require multi-row atomicity across multiple nights' inventory rows plus the reservation insert. MySQL's ACID transactions handle this natively with row-level locks.

NoSQL databases like DynamoDB offer single-item atomicity or limited multi-item transactions (up to 25 items). A 14-night stay with 14 inventory rows + 1 reservation = 15 items — possible in DynamoDB's TransactWriteItems, but each is a separate condition check, not a compound SQL condition. More complex to implement and reason about.

More importantly: our write volume (75 bookings/sec peak) is well within MySQL's capability. We do not need NoSQL's horizontal write scale. We DO need MySQL's transactional semantics. Never trade a necessary property (ACID) for an unnecessary one (massive scale beyond your requirements).

---

**Q14: How does your Redis cache invalidation work? What if invalidation fails?**

After a successful booking commit: for each night in the stay, issue `Redis DEL avail:{room_id}:{date}`. Use a pipeline for all DELs in one round trip.

If the DEL fails (Redis down or timeout): do NOT fail the booking. The booking committed to MySQL. Log the failure. The stale cache entry self-corrects when its 30-second TTL expires. The maximum window of incorrectly showing the room as available is 30 seconds.

Why DELETE instead of SET to the new count: if the cached value is already stale from an earlier miss, `cached_val - 1` writes an incorrect number. DELETE is always safe — the next read repopulates from the authoritative MySQL source with the correct current count.

---

**Q15: A guest books 5 nights. The saga's compensating transaction fails on night 3's inventory release. What is the system state and how do you fix it?**

Nights 1 and 2: inventory released (reserved_rooms decremented correctly). Night 3: compensation failed. Nights 4 and 5: not yet attempted. Reservation status: PAYMENT_FAILED. But nights 3-5 are still showing as reserved even though the booking is cancelled.

Fix: track which nights were successfully compensated. On retry, only re-attempt nights 3, 4, 5. Use an idempotent decrement guard: `WHERE reserved_rooms > 0` prevents double-decrement if the expiry job already released it.

Ultimate backstop: the expiry job (runs every minute) finds the PAYMENT_FAILED reservation and releases all remaining inventory. Maximum staleness: 1 minute.

---

**Q16: What is a deadlock? How can it occur here and how do you prevent it?**

Deadlock: Transaction A holds a lock that B needs, B holds a lock that A needs. Both wait indefinitely.

In hotel booking: Transaction A books Deluxe room then Suite room (acquires Deluxe row lock, waits for Suite). Transaction B books Suite then Deluxe (acquires Suite row lock, waits for Deluxe). Circular dependency — deadlock.

MySQL auto-detects deadlocks (~50ms) and kills one transaction. That transaction gets a deadlock error and must retry.

Prevention: always acquire row locks in the same canonical order. Before issuing UPDATEs for a multi-night booking, sort the nights by date ascending. Before a multi-room booking, sort by room_id ascending. If all transactions acquire locks in the same sequence, circular dependencies cannot form. This is a system-wide invariant, not optional.

---

**Q17: What monitoring would you add to catch a double-booking bug in production?**

**Primary canary** (every 5 minutes):
```
SELECT room_id, date FROM room_inventory WHERE reserved_rooms > total_rooms
```
`reserved_rooms > total_rooms` is physically impossible in correct operation. Any result = immediate on-call alert.

**Secondary** (daily): count confirmed reservations per (room_id, date) and compare to `total_rooms`. Any room with more confirmed bookings than capacity = double-booking confirmed.

**Real-time metric:** booking UPDATE failure rate (0 rows affected / total attempts). Healthy < 5%. If it spikes to 30%+ on a specific hotel: lock contention is abnormally high — possible bug in locking logic. Alert at 20% sustained for 60 seconds.

---

**Q18: How would you scale this to 10× write volume (750 bookings/sec)?**

At 750 bookings/sec × 100ms transaction time = 75 concurrent open connections. Against a 200-connection pool this is at the edge.

Step 1: ProxySQL or PgBouncer connection pooler — multiplexes application connections over a smaller set of database connections. Handles the connection count problem without hardware changes.

Step 2: Shard MySQL by hotel_id across 16 nodes. Each shard handles 47 bookings/sec — well within one MySQL instance's capacity.

Step 3: Per-hotel booking queue for the top-1,000 hotels by volume. Kafka topic partitioned by hotel_id. Queue consumer processes bookings serially per hotel — eliminates row-lock contention entirely. Latency cost: 100-500ms extra per booking.

Step 4: Scale booking service instances horizontally from 3 to 15 (stateless, trivial to scale).

---

**Q19: What is the difference between PENDING_PAYMENT and CONFIRMED? What does the user see during the gap?**

`PENDING_PAYMENT`: inventory decremented (room held), payment not yet confirmed. Room is unavailable to others. Booking is not finalized. TTL: 15 minutes before auto-cancel.

`CONFIRMED`: payment succeeded, reservation finalized. Room is permanently reserved for this guest.

The gap is typically 1-5 seconds (payment API call time). During this gap, "My Reservations" shows the reservation with a "Processing payment" badge and a countdown. Do not show CONFIRMED yet.

**Read-your-writes:** the user just made this booking — they must see it immediately in their reservation list. Route their "My Reservations" read to the MySQL primary (not a potentially lagged replica) for the 60 seconds following a booking. After that window, replica reads are fine.

---

**Q20: You said "0 rows affected means sold out." What if the UPDATE affected 0 rows because the room_id or date doesn't exist — not because it's sold out?**

Good catch. Two distinct causes of 0 rows affected: (1) the `AND (total_rooms - reserved_rooms) > 0` condition failed — room is sold out; (2) the `WHERE room_id = ? AND date = ?` matched no row — the room_id doesn't exist or the date isn't pre-populated.

Fix: add a pre-check before the booking transaction:

```
SELECT total_rooms, reserved_rooms FROM room_inventory
WHERE room_id = ? AND date = ?
```

If row not found: return 404 "Room or date not found." If found but available = 0: return 409 "Sold out." If found and available > 0: proceed with the UPDATE. Now 0 rows affected from the UPDATE unambiguously means a race condition (room sold out between the pre-check and the UPDATE) — return 409.

Alternatively: check the error type. "0 rows because condition failed" vs "0 rows because no matching row" can be disambiguated by running a separate `SELECT COUNT(*) WHERE room_id = ? AND date = ?` after getting 0 rows. If count = 0: the row doesn't exist (404). If count = 1: the room was taken (409).

---

*Section 5 — L5 / Senior SWE. Very high frequency at Airbnb, Booking.com, Expedia, and any company with inventory management (concerts, flights, rental cars).*  
*Full chapter. Pairs with Ch61j (Ticketing System) for the same core pattern.*

---

## Interview Simulation — Hotel Reservation System

*45-minute system design interview. Phases follow the Section 2 framework: Requirements → Estimation → API → Data Model → HLD + Deep Dive.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a hotel reservation system — something like Booking.com or Expedia. What do you want to understand first?

**Candidate:** A few clarifying questions. Are we building the full Booking.com product — search, hotel profiles, payments, reviews — or focusing on the reservation and inventory management core?

> **Interviewer:** Focus on search and reservation. Reviews and hotel management portal are out of scope.

**Candidate:** For search: are we searching across all hotels globally and returning availability, or is this "given a specific hotel and dates, show available rooms"?

> **Interviewer:** Both. Users search by city/dates to see available hotels, then drill down to a specific hotel to book a room type.

**Candidate:** The hardest part of reservation systems is preventing double-booking. What consistency guarantee do you want — is it acceptable to show a room as available, let the user fill in payment details, then fail at the last step because someone else booked it, or must availability be guaranteed at browse time?

> **Interviewer:** Soft lock at browse is fine, but the booking transaction itself must be atomic — you cannot charge two users for the same room on the same night.

**Candidate:** Good. Cancellation policies — are we supporting free cancellation within 24 hours, or is that out of scope?

> **Interviewer:** Support cancellations. Don't model the refund processing, but the room inventory must be restored.

**Candidate:** Scale: how many hotels, rooms, and peak bookings?

> **Interviewer:** 500,000 hotels globally, average 50 rooms each — 25 million rooms total. Peak booking rate at Black Friday travel sales: 1,000 bookings/second. Search is much higher — maybe 100,000 queries/second at peak.

**Candidate:** So search is 100x the write rate. This is a classic read-heavy system with a write path that requires strong consistency for the final booking step. I'll design the search path for scale and availability, and the booking path for correctness.

*(Cross-question: Explicitly naming the two paths and their different consistency requirements shows systems thinking.)*

> **Interviewer:** What's the data retention requirement?

**Candidate:** Reservation records must be kept for at least 7 years for financial compliance. Historical availability data — which rooms were available on which dates — is needed for fraud detection and analytics but can live in cold storage after 1 year.

---

### Phase 2: Estimation (4 min)

> **Interviewer:** Rough capacity estimates.

**Candidate:** **Inventory table:** one row per (hotel_id, room_type_id, date). Suppose each hotel has 5 room types and we track 365 days ahead. 500,000 hotels × 5 room types × 365 days = **912 million rows**. Each row: hotel_id (4B) + room_type_id (4B) + date (3B) + total_rooms (2B) + reserved_rooms (2B) = ~15 bytes. That is about **14 GB** for the inventory table — fits in a well-indexed relational database, maybe two shards.

**Reservation table:** 1,000 bookings/second × 86,400 seconds/day = **86 million new reservations/day**. Average stay 3 nights, so 86M rows/day. After 7 years: ~220 billion rows. Hot data (last 90 days) is ~7.7 billion rows — this needs sharding or a purpose-built storage system.

**Search QPS:** 100,000 peak queries/second. Cannot hit the database directly. Need a search cache layer.

*(Cross-question: Candidate correctly identifies that the inventory table is manageable in RDBMS but the reservation history table needs a different strategy.)*

---

### Phase 3: API Design (4 min)

> **Interviewer:** Define the key API endpoints.

**Candidate:** Three core endpoints:

**1. Search hotels:**
```
GET /v1/hotels/search
  ?city=Paris
  &check_in=2025-08-10
  &check_out=2025-08-13
  &guests=2
  &room_type=double      # optional
  &page=1&limit=20
```
Returns a list of hotels with available room counts and price ranges. This is the high-QPS read path — served from cache.

**2. Get room availability for a specific hotel:**
```
GET /v1/hotels/{hotel_id}/availability
  ?check_in=2025-08-10
  &check_out=2025-08-13
  &room_type=double
```
Returns available room count and price per night. This is the step before booking — user sees "3 rooms left."

**3. Create reservation:**
```
POST /v1/reservations
Body: {
  "hotel_id": "hotel_123",
  "room_type_id": "double_standard",
  "check_in": "2025-08-10",
  "check_out": "2025-08-13",
  "guest_count": 2,
  "payment_token": "tok_visa_abc123"
}
```
Returns reservation_id and confirmation number on success. Returns 409 Conflict if room is no longer available.

**4. Cancel reservation:**
```
DELETE /v1/reservations/{reservation_id}
```
Restores inventory and processes refund if eligible.

---

### Phase 4: Data Model (4 min)

> **Interviewer:** Design the core tables.

**Candidate:** Four tables:

**hotels:** hotel_id, name, city, star_rating, lat, lon, amenities_json

**room_types:** room_type_id, hotel_id, name (single/double/suite), base_price_cents, max_guests, total_rooms_count

**room_inventory:** (the hot table for bookings)
```sql
room_inventory (
  hotel_id       INT,
  room_type_id   INT,
  date           DATE,
  total_rooms    SMALLINT,
  reserved_rooms SMALLINT,
  PRIMARY KEY (hotel_id, room_type_id, date)
)
```
Available rooms = total_rooms - reserved_rooms. Atomic decrement using `UPDATE ... SET reserved_rooms = reserved_rooms + 1 WHERE reserved_rooms < total_rooms`.

**reservations:**
```sql
reservations (
  reservation_id  BIGSERIAL PRIMARY KEY,
  user_id         BIGINT,
  hotel_id        INT,
  room_type_id    INT,
  check_in        DATE,
  check_out       DATE,
  status          ENUM('PENDING','CONFIRMED','CANCELLED'),
  payment_id      BIGINT,
  created_at      TIMESTAMPTZ
)
```

> **Interviewer:** Why reserved_rooms increment instead of a row-per-room-per-night?

**Candidate:** Row-per-room-per-night (e.g., a `room_assignments` table with one row per physical room per night) is more flexible but creates a hot-row contention problem: for a hotel with 200 rooms, a Friday night booking requires scanning 200 rows to find an available one, then locking one row. With the counter approach, I touch exactly one row per (hotel, room_type, date) and the UPDATE is atomic at the row level. The counter approach has one limitation: it cannot track which specific physical room a guest gets — but that assignment is done by the hotel's property management system at check-in, not by us.

*(Cross-question: This is a common follow-up — the candidate should explain why the simpler model is correct for this use case.)*

---

### Phase 5: HLD + Deep Dive (15 min)

> **Interviewer:** Draw the architecture and walk through a booking flow end to end.

**Candidate:**

```
                    ┌────────────────────────────────────────────────┐
                    │                   Client                        │
                    └──────────────────────┬─────────────────────────┘
                                           │
                    ┌──────────────────────▼─────────────────────────┐
                    │             API Gateway / CDN                   │
                    └──────┬────────────────────────────┬────────────┘
                           │                            │
              ┌────────────▼──────────┐   ┌────────────▼──────────┐
              │    Search Service     │   │  Reservation Service   │
              │   (100K QPS reads)    │   │  (1K bookings/sec)     │
              └────────────┬──────────┘   └────────────┬──────────┘
                           │                            │
              ┌────────────▼──────────┐   ┌────────────▼──────────┐
              │  Elasticsearch        │   │  Reservation DB        │
              │  (hotel + avail idx)  │   │  (PostgreSQL, sharded) │
              │  + Redis L1 cache     │   │  room_inventory +      │
              └───────────────────────┘   │  reservations tables   │
                                          └────────────┬──────────┘
                                                       │
                                          ┌────────────▼──────────┐
                                          │   Payment Service      │
                                          │  (Stripe/Braintree)    │
                                          └───────────────────────┘
                                                       │
                                          ┌────────────▼──────────┐
                                          │  Notification Service  │
                                          │  (email / SMS confirm) │
                                          └───────────────────────┘
```

> **Interviewer:** Walk through a booking. User selects a double room at Hotel Paris for Aug 10-13.

**Candidate:** The booking path is the correctness-critical path, so I'll be precise:

**Step 1 — Check availability (GET /hotels/hotel_123/availability):**
Reservation Service queries `room_inventory` for (hotel_123, double_standard, [Aug 10, Aug 11, Aug 12]). All three dates must have `reserved_rooms < total_rooms`. This is a read — returns "3 available."

**Step 2 — Initiate booking (POST /reservations):**
The Reservation Service executes a **database transaction** across three steps:

```sql
BEGIN;
-- Lock the inventory rows for all nights (pessimistic lock)
SELECT * FROM room_inventory
  WHERE hotel_id = 123 AND room_type_id = 42
  AND date IN ('2025-08-10', '2025-08-11', '2025-08-12')
  FOR UPDATE;

-- Verify availability for all nights
-- (fail with 409 if any night has reserved_rooms = total_rooms)

-- Increment reservation counter for each night
UPDATE room_inventory
  SET reserved_rooms = reserved_rooms + 1
  WHERE hotel_id = 123 AND room_type_id = 42
  AND date IN ('2025-08-10', '2025-08-11', '2025-08-12')
  AND reserved_rooms < total_rooms;

-- Create the reservation record in PENDING state
INSERT INTO reservations (...) VALUES (...) RETURNING reservation_id;
COMMIT;
```

**Step 3 — Payment:**
Outside the DB transaction, call Payment Service with the payment_token. If payment succeeds: `UPDATE reservations SET status = 'CONFIRMED'`. If payment fails: `UPDATE reservations SET status = 'CANCELLED'` and `UPDATE room_inventory SET reserved_rooms = reserved_rooms - 1` (rollback the inventory).

**Step 4 — Notification:**
Publish `reservation.confirmed` event to Kafka. Notification Service sends confirmation email asynchronously.

> **Interviewer:** Why do you use pessimistic locking (`SELECT FOR UPDATE`) here? You mentioned optimistic locking earlier as an option.

**Candidate:** For multi-night bookings, I need to lock multiple rows atomically. With optimistic locking (version counter), I'd read all three inventory rows, compute new counts, then attempt to UPDATE each with a WHERE version = old_version check. The problem: if the first night's UPDATE succeeds but the second night's UPDATE fails (someone else booked the last room on Aug 11), I have a partial update and need compensating transactions to undo the first night. That is complex. `SELECT FOR UPDATE` acquires row-level locks for all three nights in one step before any modification — simpler, and the lock duration is short (the transaction runs in under 50ms). Pessimistic locking has a risk of deadlock if two transactions try to lock the same nights in different orders — I prevent this by always sorting nights in ascending date order before acquiring locks.

*(Cross-question: Naming the specific deadlock risk and the fix — ordered locking — is the differentiating answer.)*

---

### Common Cross-Questions and Strong Answers

> **Interviewer:** What happens if the server crashes between the DB transaction commit and the Payment Service call? The inventory is decremented but no payment was taken.

**Candidate:** This is the classic "write-ahead saga" problem. The reservation record is in `PENDING` state in the DB. I have a background **cleanup job** that runs every 5 minutes and finds reservations stuck in PENDING for more than 10 minutes. For each, it either: (a) retries the payment if the payment_token is still valid, or (b) cancels the reservation and restores inventory with `reserved_rooms = reserved_rooms - 1`. The 10-minute window is the maximum time a PENDING reservation holds inventory. Users see "reserving..." for at most 10 minutes before a definitive result. This is the same pattern Stripe uses for two-phase payment authorization: authorize (hold inventory + reserve funds) then capture (confirm booking + charge card).

*(Cross-question: Naming the "payment hold vs. charge" pattern — authorize then capture — is the expert-level answer here.)*

> **Interviewer:** Your inventory table has 912 million rows. A SELECT with FOR UPDATE on 3 rows across this table — how fast is that?

**Candidate:** With the composite primary key `(hotel_id, room_type_id, date)`, the SELECT FOR UPDATE is a point lookup on the clustered index — O(log N) which at 912M rows is about 30 B-tree levels, roughly 3-5 ms including I/O. The rows for a 3-night stay are physically adjacent in the index (same hotel_id, same room_type_id, consecutive dates), so all 3 rows likely share the same or adjacent index pages — likely a single I/O. Total transaction time including the UPDATE and INSERT is under 20ms. This is well within acceptable SLA for a booking endpoint.

> **Interviewer:** How do you handle the search path — 100,000 QPS looking for hotels in Paris with availability for Aug 10-13?

**Candidate:** The search path and booking path are separated by design. Search goes through Elasticsearch (or a denormalized read replica) with Redis caching. When a user searches "Paris, Aug 10-13, 2 guests," the query is: find hotels in Paris where at least one room type has available rooms on all three nights. Pre-computing a `hotel_availability` summary table that rolls up `room_inventory` nightly (via an ETL pipeline) and indexing it in Elasticsearch gives us sub-50ms search at 100K QPS. The summary is stale by up to 1 hour — acceptable for search. The availability check on the specific hotel page (the GET /hotels/{id}/availability endpoint) hits the live `room_inventory` table and is always fresh. This two-tier model — approximate availability for search, exact availability for booking — is how every real hotel platform works.

> **Interviewer:** A hotel decides to run a flash sale — 50% off all rooms for the next 10 minutes. How does this affect your system?

**Candidate:** Flash sales are a write amplification problem. If Hotel Grand Paris has 1,000 rooms and a flash sale pushes 10,000 users to the booking page simultaneously, the `room_inventory` table for that hotel gets hammered with concurrent `SELECT FOR UPDATE` + `UPDATE` transactions. Mitigation: (1) **Rate limit per hotel_id** — cap concurrent booking transactions for any single hotel at, say, 200/second. Excess requests get queued or receive a "high demand, retry in 5 seconds" response. (2) **Redis-backed inventory counter** — for flash sale hotels, move the available_rooms counter into Redis using `DECR` (atomic, lock-free, ~100K ops/sec). When the Redis counter hits 0, stop accepting bookings. Write the final booked count to PostgreSQL asynchronously. The risk is Redis failing — mitigate with Redis persistence (AOF) and a reconciliation job. (3) Use a **queue-based booking flow** for large hotels: accept bookings into a Kafka queue and process serially, giving users a "position in queue" progress indicator. Airbnb uses this approach for extremely popular listings.
