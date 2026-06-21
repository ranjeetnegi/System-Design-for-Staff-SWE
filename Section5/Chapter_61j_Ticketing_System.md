# Chapter 61j: Ticketing System — Ticketmaster / Concert Seats

> When Taylor Swift tickets go on sale, 14 million people hit "buy" in the
> first minute. Your database has 60,000 seats. You need to sell exactly
> 60,000 tickets — not 59,999, not 60,001 — while every user thinks
> they're first in line.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Ticketing System                           |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (assigned seats? queuing? transfers?) |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                           |
|                                                                  |
|  The clarifying question that changes everything:                |
|  "Is this assigned seating (each user picks a specific seat)   |
|   or general admission (just X tickets, no seat selection)?"   |
|   Assigned seating: 60K individual rows to lock. General        |
|   admission: one counter to decrement. Very different problem.  |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Atomic seat hold: UPDATE WHERE status='AVAILABLE', check     |
|    rows_affected == 1 (not 0)                                   |
|  - 10-minute hold expiry with background release job            |
|  - Virtual waiting room (Redis queue) at flash sale start       |
|  - Saga for payment failure (compensating hold release)         |
|  - Idempotency key per purchase attempt                         |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Multi-region for global on-sale events (split inventory)     |
|  - Dynamic pricing: price adjusts with demand during sale       |
|  - Queue fairness guarantees (verified randomization vs FIFO)   |
|  - Bot detection at queue entry (distinguishing humans vs bots) |
|  - Ticket transfer and secondary market integration             |
+------------------------------------------------------------------+
```

---

## Why This Chapter Matters

The ticketing system question is asked at companies running any kind of limited-inventory, high-demand sale: Ticketmaster, StubHub, e-commerce flash sales (sneakers, limited editions), hotel bookings, and restaurant reservations. The core problem — "how do you prevent selling more seats than exist while handling 10 million concurrent users" — directly teaches optimistic locking, the hold-confirm pattern, and traffic shaping.

This chapter pairs with Ch61d (Hotel Reservation) but at a fundamentally different scale: hotel reservations have thousands of rooms and moderate load; ticket sales have 60,000 seats and 14 million users hitting simultaneously at T=0. The queue problem is what makes ticketing unique.

Interviewers reward candidates who immediately say: "The core problem is that checking availability and claiming a seat must be a single atomic operation. If I read 'available' and then write 'reserved' as two separate steps, two users can both read 'available' simultaneously and both succeed — overselling the seat."

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify first

1. "Assigned seating (user picks A12) or general admission (just 'I want 2 tickets')?" This changes the locking model completely.
2. "When does the sale open? Is it always a flash sale (everyone at T=0) or rolling?" Flash sale design requires a virtual queue.
3. "What is the hold duration? 10 minutes is standard, but some systems use 30 minutes."
4. "Ticket transfer and resale? This adds a completely different set of state transitions."

For this chapter: assigned seating, flash sale (10M users at T=0), 10-minute hold, no resale in scope.

### Who uses the ticketing system?

**Buyers:**
- Fans trying to buy Taylor Swift concert tickets at 10am when the sale opens
- Corporate buyers purchasing blocks of sports event seats
- Last-minute buyers grabbing remaining tickets days before the event

**Event organizers:**
- Concert promoters setting up an event with section/row/seat structure and price tiers
- Sports teams managing season ticket holder allocations before general public sale

**Internal systems:**
- Payment system: processes the credit card charge (Ch58 — out of scope here)
- Notification system: sends confirmation emails and digital tickets
- Fraud detection: identifies bot purchases

### Core use cases

**P0 — Must have:**
- UC1: User enters the virtual queue at T=0 → receives a queue position
- UC2: User reaches the front of queue → browses available seats on a seat map
- UC3: User selects a seat → seat atomically marked as HELD for 10 minutes
- UC4: User completes payment → seat marked SOLD, ticket issued
- UC5: 10-minute hold expires without payment → seat automatically released

**P1 — Important:**
- UC6: View seat map with real-time availability (green = available, red = held/sold)
- UC7: View booking history and download ticket (barcode/QR code)
- UC8: Multiple seats: hold all seats or none (atomic multi-seat hold)

**Out of scope:**
- Payment processing (Ch58)
- Ticket transfer and resale
- Bot detection
- Dynamic pricing changes during sale

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Sale operations

- **F1:** `join_queue(user_id, event_id) -> queue_position, estimated_wait_seconds`
- **F2:** `get_queue_status(user_id, event_id) -> position, wait_estimate, entry_token (if ready)`
- **F3:** `get_seat_map(event_id, section) -> [(seat_id, row, seat, price, status), ...]`
- **F4:** `hold_seat(seat_id, user_id, entry_token) -> hold_id, expires_at` (or "seat unavailable")
- **F5:** `confirm_purchase(hold_id, payment_confirmation) -> ticket_id, barcode` (or "hold expired")
- **F6:** `release_hold(hold_id, user_id)` — user explicitly releases without purchasing

### The core atomicity requirement

```
What CANNOT work:

Step 1: SELECT status FROM seats WHERE seat_id = 'A12'
Step 2: If status == 'AVAILABLE': INSERT INTO holds (seat_id, user_id, expires_at)

Problem: between step 1 and step 2, another user's step 1 can execute.
  User A reads: A12 is AVAILABLE.
  User B reads: A12 is AVAILABLE. (same moment!)
  User A writes: hold for A12.
  User B writes: hold for A12. (BOTH succeed! Seat A12 is now double-held.)

What MUST work: single atomic statement that both checks AND updates.

The correct approach:
  UPDATE seats SET status='HELD', held_by='user_A', hold_expires=NOW()+10min
  WHERE seat_id='A12' AND status='AVAILABLE'
  
  Check: rows_affected == 1 -> success (we got the seat)
  Check: rows_affected == 0 -> failure (seat taken)
  
  If user A and user B both execute this simultaneously:
    Database row-level locking guarantees only ONE update succeeds.
    The other gets rows_affected = 0.
    Zero races. Zero overselling.
```

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### The flash sale math

```
T=0 event: Taylor Swift, 60,000 seat stadium.
Expected buyers: 14,000,000 (14 million unique users trying)

Requests in the first minute:
  14M users * avg 3 requests/user/minute (queue join + status checks) = 42M req/min = 700K req/sec

Database writes (seat holds):
  60,000 seats / 10 minutes = 6,000 seat holds per minute = 100 seat holds/sec
  (After virtual queue, each user that reaches the hold step tries exactly once)
  With retry on "seat unavailable": maybe 300 hold attempts/sec at peak

Database reads (seat map):
  Each user views the seat map while selecting.
  Seat map: 60,000 seats. If served from cache: 60K entries read at once.
  10,000 users viewing seat map simultaneously: 10,000 cache reads/sec.
  This is the easy part — caching solves it.

Real bottleneck: the 700K req/sec at T=0.
  Without queue: 700K users all hitting the database at once.
  Even if 99% are queue status checks (not DB writes): 7K DB writes/sec still possible.
  A typical Postgres instance: 10-30K writes/sec. Might survive. Might not.
  
  The problem is unpredictability: what if 99.9% of 14M users all get through the queue in 1 minute?
  The virtual queue exists to make the database see a CONTROLLED, PREDICTABLE rate.
```

### Seat data size

```
60,000 seats per event:
  Per seat: seat_id (8 bytes) + section (4 bytes) + row (4 bytes) + seat_num (4 bytes)
            + price (8 bytes) + status (1 byte) + held_by (16 bytes, UUID) + hold_expires (8 bytes)
  Total: ~53 bytes per seat
  
  Total seat data: 60,000 * 53 bytes = ~3 MB
  
  Fits entirely in Redis cache: SET seat:{seat_id} {status_json} EX 30
  Or as a Redis hash: HSET event:{event_id}:seats seat_id status ...
  At 3 MB: one Redis instance holds millions of events' seat status in memory.
  
  Seat map display: return all 60,000 seats for an event.
  3 MB response per user viewing full map. Usually paginated by section.
  Per section (10 sections): 6,000 seats * 53 bytes = 318 KB per section view.
```

### Queue math

```
Virtual queue: 14M users join at T=0.
  Redis INCR queue:event_123:position -> returns 1, 2, 3, ... 14,000,000
  Each user gets a position number. O(1) per INCR. Redis: 1M+ INCR/sec.
  14M users all hitting INCR: saturates Redis (1M/sec capacity) -> takes 14 seconds.
  Fix: pre-generate position tokens in Redis pipeline. Or: batch position assignment.
  
  Actually: 14M users don't all arrive in the exact same millisecond.
  Arrival spread: ~30 seconds as users refresh and click at slightly different times.
  14M users / 30 seconds = 467K users/second arriving at queue.
  At 467K INCR/sec: within Redis capacity (500K+ simple ops/sec). Fine.

Release rate: how fast do we let users through the queue?
  Target: handle 1,000 users entering the sale per second (this is the "safe" rate for the seat DB).
  At 1,000 entries/sec and 60,000 seats: sale completes in 60 seconds (if all seats sell).
  Total queue time for user at position 14,000,000: 14M / 1,000 = 14,000 seconds = ~4 hours.
  Most users will be disappointed.
  
  In practice: not all 14M users convert to purchases. Many browse and leave.
  Effective conversion rate: ~0.5% (many casual lookers, not all 14M are serious buyers).
  Serious buyers: 14M * 0.5% = 70,000 (~60,000 seats + 17% extra for abandoned holds).
  
  Even so: the queue must handle all 14M users fairly.
```

---

## Phase 4: Non-Functional Requirements (Minutes 14-19)

### Correctness (most important)

- **No overselling:** Never sell more than N tickets. This is a hard invariant. One atomicity violation = unsatisfied customer + refunds + PR disaster.
- **No double-charging:** If a user's payment fails and they retry, they must not be charged twice for the same seat. Idempotency key per purchase attempt.
- **Hold expiry:** If a user holds a seat but does not complete payment within 10 minutes, the hold MUST be released. No seat left permanently held.

### Performance

- Queue join response: < 500ms (just a Redis INCR — should be 10ms in practice)
- Seat hold response: < 1 second (one DB write + Redis update)
- Seat map display: < 500ms (served from Redis cache)
- Hold expiry background job: runs every 30 seconds

### Availability

- 99.9% during the sale period (the most critical window — minutes around T=0).
- Before/after sale: 99.5% acceptable.

### Fairness

- Users who join the queue earlier should have a higher chance of getting tickets.
- Random shuffling within arrival windows (5-second buckets) to prevent "first millisecond advantage" unfairness (users with lower network latency would always be first otherwise).

---

## Phase 5: Assumptions and Constraints

- A1: Assigned seating (each seat has an ID and physical location in the venue).
- A2: Maximum hold duration: 10 minutes. Hard cutoff — no extensions.
- A3: A user can hold at most 4 seats simultaneously (standard anti-scalping policy).
- A4: Hold is per-device, not per-account (one hold per browser session, not per user ID). Multiple devices can hold different seats for the same user — this is a policy decision (antifraud takes care of it).
- A5: Once a seat is SOLD, it cannot be returned to AVAILABLE in this design (refunds are handled separately by a cancellation flow).
- A6: The payment service is external (Ch58). We receive a webhook callback on payment success/failure.

---

## Architecture Design — HLD

### Opening analogy

Imagine a stadium with 60,000 numbered turnstiles. Before the gates open, 14 million people are outside. Rather than letting them all rush the gates simultaneously (chaos, injuries, people double-occupying seats), a security system assigns everyone a numbered ticket ("you are position 4,231,089") and opens the gates 1,000 people at a time. Once inside, each person must touch their desired turnstile before anyone else. Only one person can touch any turnstile — the turnstile locks with a 10-minute timer. If you do not pay within 10 minutes, the turnstile resets and the next person can try.

The turnstile locking is the atomic database UPDATE. The numbered tickets outside are the virtual queue.

### Full HLD diagram

```
[14M Users at T=0]
        |
        | join_queue request
        v
+------------------+
|  QUEUE SERVICE   |
|                  |
|  Redis INCR ->   |
|  position number |
|  JWT entry token |
|                  |
|  Rate limiter:   |
|  1,000 users/sec |
|  enter the sale  |
+------------------+
        |
        | entry token (when position reached)
        v
+------------------+     +------------------+
|  SEAT SERVICE    |     |  REDIS CACHE     |
|                  |<--->|                  |
|  - hold_seat()   |     |  seat status map |
|  - atomic UPDATE |     |  event:{id}:seats|
|  - release expiry|     |  AVAILABLE/HELD/ |
|                  |     |  SOLD per seat   |
+------------------+     +------------------+
        |                        ^
        | successful hold        | invalidate on change
        v
+------------------+     +------------------+
|  ORDER SERVICE   |     |  POSTGRES DB     |
|                  |---->|                  |
|  Saga:           |     |  seats table     |
|  hold->pay->     |     |  orders table    |
|  confirm         |     |  holds table     |
|                  |     |                  |
|  Payment webhook |     |                  |
|  handler         |     +------------------+
+------------------+
        |
        | Kafka: order-events
        v
+------------------+
|  NOTIFICATION    |
|  SERVICE         |
|  email + ticket  |
|  (QR code)       |
+------------------+

[WebSocket Server]
  -> pushes seat status changes to browsing users in real-time
  -> user sees seats turn red (held) or green (released) on seat map
```

### Component responsibilities

```
+-------------------+----------------------------------+-----------+------------------+
| Component         | Responsibility                   | Stateful? | Scale target     |
+-------------------+----------------------------------+-----------+------------------+
| Queue Service     | Issues position numbers, manages | YES       | 467K joins/sec   |
|                   | entry rate limiting, entry tokens | (Redis)   | (Redis INCR)     |
+-------------------+----------------------------------+-----------+------------------+
| Seat Service      | Atomic seat hold/release, expiry | NO        | 1K holds/sec     |
|                   | background job                   |           | (controlled rate)|
+-------------------+----------------------------------+-----------+------------------+
| Order Service     | Saga orchestration: hold->pay->  | NO        | 1K orders/sec    |
|                   | confirm, payment webhook handler  |           |                  |
+-------------------+----------------------------------+-----------+------------------+
| Redis             | Seat status cache, queue counters| YES       | 14M queue + seat |
|                   | session state, dedup cache        |           | cache for events |
+-------------------+----------------------------------+-----------+------------------+
| PostgreSQL        | Seats, holds, orders — source of | YES       | 1K writes/sec    |
|                   | truth for all transactions        |           | (post-queue)     |
+-------------------+----------------------------------+-----------+------------------+
| WebSocket Servers | Push seat status changes to users| YES       | 10K connections  |
|                   | browsing the seat map             |           | per server       |
+-------------------+----------------------------------+-----------+------------------+
| Kafka             | Order events: payment triggers,  | YES       | 1K events/sec    |
|                   | notification triggers             |           | RF=3             |
+-------------------+----------------------------------+-----------+------------------+
```

---

## Component 1: The Atomic Seat Hold — Preventing Overselling

**This is the entire chapter in one SQL statement. Master it.**

### The wrong approach (and why it fails)

```
Wrong two-step approach:
  Step 1: SELECT status FROM seats WHERE seat_id = 'A12'
    -- Result: 'AVAILABLE' ✓
  Step 2: INSERT INTO holds VALUES ('A12', 'user_A', NOW()+10min)
    -- Succeeds ✓

Problem: 1,000 users simultaneously execute Step 1 for seat A12.
  All 1,000 users read: status = 'AVAILABLE'.
  Then all 1,000 users execute Step 2.
  1,000 INSERT statements succeed (or the first one succeeds and the rest fail on FK constraint).
  Even with a unique constraint on seat_id in holds: 1 user gets the seat,
  999 users get an error after already being told "seat available."
  That is a terrible user experience AND a potential double-sell vulnerability.

The fundamental race: read-then-write is not atomic.
```

### The correct single-statement atomic hold

```
SQL for single seat hold:
  UPDATE seats
  SET status      = 'HELD',
      held_by     = 'user_A',
      hold_expires = NOW() + INTERVAL '10 minutes'
  WHERE seat_id = 'A12'
    AND status = 'AVAILABLE'

Check: affected_rows = 1 -> success. Seat A12 is held.
Check: affected_rows = 0 -> failure. Seat A12 was already HELD or SOLD.

Why this is atomic:
  The database acquires a row-level exclusive lock on the row for seat A12 at the start
  of the UPDATE statement. No other transaction can modify or lock the same row until this
  UPDATE commits. If two transactions try to UPDATE seat A12 simultaneously:
    Transaction 1: acquires lock, reads status='AVAILABLE', writes status='HELD'. Commits. Releases lock.
    Transaction 2: acquires lock (after T1 releases), reads status='HELD'. WHERE status='AVAILABLE' is FALSE.
    Rows affected: 0. No update occurs. Transaction 2 knows the seat is taken.

This is a "compare-and-swap" (CAS) at the database level.
The WHERE clause is the "compare." The SET is the "swap." They happen atomically.
```

### Multi-seat hold (user wants 4 tickets together)

```
Challenge: user wants seats A12, A13, A14, A15 together.
  If we hold them one-by-one: we might hold A12, A13, A14, then fail on A15 (taken).
  Result: user holds 3 seats they can't use. Inventory deadlocked.
  
  Must hold all 4 or none (atomic multi-seat hold).

Approach 1: Serializable isolation + SELECT FOR UPDATE + conditional UPDATE
  BEGIN;
  SELECT seat_id FROM seats
  WHERE seat_id IN ('A12', 'A13', 'A14', 'A15')
    AND status = 'AVAILABLE'
  FOR UPDATE;
  -- If all 4 rows returned (all available): proceed
  -- If fewer than 4 returned: ROLLBACK (at least one seat taken)
  
  UPDATE seats SET status='HELD', held_by='user_A', hold_expires=NOW()+10min
  WHERE seat_id IN ('A12', 'A13', 'A14', 'A15');
  COMMIT;

  SELECT FOR UPDATE: acquires exclusive row locks on all 4 rows.
  Other transactions trying to hold any of these seats block until this transaction commits or rolls back.

Approach 2: Batch UPDATE with count check
  UPDATE seats SET status='HELD', held_by='user_A', hold_expires=NOW()+10min
  WHERE seat_id IN ('A12', 'A13', 'A14', 'A15')
    AND status = 'AVAILABLE'
  
  Check: rows_affected == 4 -> all 4 available -> hold successful.
  Check: rows_affected < 4 -> at least one taken.
    Compensate: UPDATE seats SET status='AVAILABLE', held_by=NULL, hold_expires=NULL
    WHERE seat_id IN ('A12', 'A13', 'A14', 'A15') AND held_by = 'user_A'
    (Undo the partial hold.)
  
  Problem: between the partial hold and the undo, another user might try to hold one of the partially-held seats.
  They get rows_affected = 0 even though the seat will be available again shortly.
  This is a brief false-negative ("seat appears taken but will be released in milliseconds").
  Acceptable in practice.

Deadlock prevention for multi-seat holds:
  Always acquire row locks in sorted order (by seat_id).
  User A holds A12, A13, A14. User B holds A13, A14, A15.
  Without ordering: A locks A12, A13, A14; B locks A14 first, waits for A13 -> deadlock.
  With ordering (both sort by seat_id): A locks A12 first, then A13, A14, A15.
  B also locks A12 first -> blocked by A. A finishes -> B proceeds in order. No deadlock.
```

### Seat status in Redis cache

```
On every status change (AVAILABLE -> HELD -> SOLD -> AVAILABLE):
  Update Postgres (source of truth).
  Update Redis cache: HSET event:{event_id}:seats seat_id {status}

On Redis cache miss (cold start or eviction):
  Load all seat statuses from Postgres for that event.
  SET event:{event_id}:seats ... with EX 60 (60-second TTL).
  Any subsequent status change invalidates by updating the hash field.

Seat map display:
  HGETALL event:{event_id}:seats -> all 60K seat statuses as a hash map.
  Response: {A12: "HELD", A13: "AVAILABLE", A14: "SOLD", ...}
  Client renders each seat's color based on status.
  
  If Redis is unavailable: fall back to direct Postgres read.
    SELECT seat_id, status FROM seats WHERE event_id = ? 
    Returns 60,000 rows. ~3 MB. Takes 200-500ms from DB. Acceptable as fallback.
```

---

## Component 2: The Virtual Queue — Traffic Shaping at T=0

**Without this, 14M users would overwhelm the seat service database.**

### Why a virtual queue?

```
Without queue:
  T=0: 14M users send "hold seat A12" simultaneously.
  Seat service: 14M concurrent requests -> connection pool exhausted -> timeout -> retry.
  Database: 14M concurrent UPDATE attempts on seats table.
  Even with connection pooling (1,000 DB connections): 14,000 queued requests per connection.
  Each request: 10ms DB time. Queue depth: 14,000 * 10ms = 140 seconds per connection.
  All 14M users wait > 2 minutes for a simple "seat taken" response.
  
  Meanwhile: the database is thrashing. Connection timeouts. DB OOM. Crash.

With virtual queue:
  T=0: 14M users send "join queue" to Queue Service.
  Queue Service: Redis INCR -> returns position number. 467K INCs/sec. Handles it.
  Each user gets their position and an estimated wait time.
  Queue Service releases 1,000 users per second to the Seat Service.
  Seat Service: 1,000 req/sec. Well within DB capacity.
  Database: controlled, predictable write rate.
```

### Queue implementation

```
Redis data structures for the queue:

1. Position counter:
   Key: queue:{event_id}:position_counter
   INCR queue:{event_id}:position_counter -> returns 1, 2, 3, ... 14,000,000
   This is O(1) in Redis. 500K INCs/sec is achievable.

2. User position storage:
   Key: queue:{event_id}:user:{user_id}
   Value: {position: 4231089, joined_at: 1735000000, fingerprint: abc123}
   TTL: 2 hours (event sale duration)

3. Current release position:
   Key: queue:{event_id}:release_position
   Value: the position currently being served (monotonically increasing)
   Queue Releaser Service: every second, INCR queue:{event_id}:release_position by 1000
   (Releases 1000 positions per second)

User flow:
  T=0:   User hits "join queue" button.
  App:   POST /queue/{event_id}/join
  Queue Service: 
    pos = INCR queue:{event_id}:position_counter  -> 4231089
    SET queue:{event_id}:user:{user_id} {pos, joined_at} EX 7200
    current_release = GET queue:{event_id}:release_position  -> 100000
    wait_seconds = (pos - current_release) / 1000  -> (4231089-100000)/1000 = 4131s = 68 min
    Return: {position: 4231089, estimated_wait: "68 minutes"}

  T+4131s: User's position is reached.
    GET queue:{event_id}:release_position -> 4231000 (close enough)
    User receives: entry token (JWT signed with event_id + user_id + position + expiry)
    Entry token is valid for 15 minutes (user must enter the seat selection within 15 min of being let in)

  User enters seat selection:
    GET /events/{event_id}/seats?token={entry_token}
    Server validates: JWT signature valid, event_id matches, not expired.
    Returns seat map. User proceeds to select and hold.
```

### Queue fairness and anti-bot

```
Problem: bots can run thousands of simultaneous queue joins, claiming positions 1-1000 and
then selling or using those early positions.

Solution 1: Rate limit queue joins per IP address.
  Max 1 queue join per IP per event.
  Redis: SET ratelimit:queue:{event_id}:{ip} 1 NX EX 3600
  If key already exists: reject join with "you are already in the queue."

Solution 2: CAPTCHA at queue entry.
  Solve a CAPTCHA before joining the queue (at T=0, when load is highest).
  CAPTCHA: Google reCAPTCHA v3 (invisible scoring) or hCaptcha.
  Bots without valid CAPTCHA tokens are rejected at the API gateway.

Solution 3: Random shuffle within time windows.
  Instead of strict FIFO (position = arrival time in milliseconds):
  Bucket arrivals into 5-second windows.
  Within each 5-second window: randomly shuffle positions.
  Result: all users who joined in the same 5-second window have equal chance.
  No advantage to having the lowest network latency (< 1ms vs 5ms is irrelevant within a 5s window).

Solution 4: Account age verification.
  New accounts (created in the last 24 hours) can join the queue but cannot complete purchase without ID verification.
  Bots create fresh accounts. This reduces their success rate.
```

---

## Component 3: Hold Expiry — Releasing Abandoned Seats

### Background job design

```
Seats can be HELD but never converted to SOLD if:
  - User abandons the payment page
  - User's browser closes
  - Payment service is down (user cannot complete)
  - User decides they don't want the seat

All held seats must be released after 10 minutes.

Background job (runs every 30 seconds):
  UPDATE seats
  SET status     = 'AVAILABLE',
      held_by    = NULL,
      hold_expires = NULL
  WHERE status = 'HELD'
    AND hold_expires < NOW()
  RETURNING seat_id  -- (Postgres-specific: returns the released seats)

  Performance: this query uses the index on (status, hold_expires).
  At 1,000 holds/sec with 10-minute TTL: at any time, up to 600,000 rows in HELD status.
  Index scan for hold_expires < NOW(): O(log N + expired_count). Fast.
  Released seats count: at 1,000 holds/sec with 90% purchase rate: 10% abandon = 100 seats/sec expired.
  Over 10 minutes: 60,000 total released. This is manageable.

After release: invalidate Redis cache for the released seats.
  For each returned seat_id: HSET event:{event_id}:seats {seat_id} "AVAILABLE"
  Push WebSocket notification: "seat A12 is now available" -> browsing users see the seat turn green.
```

### Why not use Redis TTL for hold expiry?

```
Appealing option: store holds in Redis with TTL instead of Postgres.
  SETEX hold:{seat_id} 600 {user_id}  (expire in 600 seconds)
  On TTL expiry: seat automatically "released."
  
  Problems:
  1. Durability: Redis (without AOF) can lose data on crash. Holds lost = seats "stuck"
     in HELD state with no record of who held them. Or: Redis says AVAILABLE but Postgres says HELD.
     Inconsistency.
  2. TTL precision: Redis TTL has 1-second granularity. A hold set for 600 seconds
     might expire in 599 or 601 seconds. For payment processing, 1 second matters.
  3. Audit trail: "who held seat A12 and when" must be queryable for disputes.
     Redis (in-memory) is not suited for audit logs. Postgres is.
  
  Correct: use Postgres as the authoritative hold store (with hold_expires column).
  Redis caches the current status (AVAILABLE/HELD/SOLD) for fast seat map display.
  Background job reads from Postgres and releases expired holds.
  Redis cache is refreshed by the background job after each release.
```

---

## Component 4: The Saga Pattern — Payment Failure Handling

### The two-phase commit problem

```
Three operations must happen in sequence:
  1. Hold seat (Seat Service + DB)
  2. Charge payment (Payment Service — external)
  3. Confirm ticket (Order Service + DB, mark seat SOLD, issue ticket)

If all succeed: great. If any fail: compensate.

Why not 2PC (two-phase commit)?
  2PC requires the Seat Service and Payment Service to coordinate via a transaction manager.
  Payment Service is external (Stripe, Braintree). It does not participate in our 2PC.
  External services cannot be included in a distributed transaction.
  2PC is also slow and fragile. The saga pattern is better.
```

### Choreography-based saga

```
Events and compensations:

Step 1: Hold seat.
  Seat Service: UPDATE seats... WHERE status='AVAILABLE' -> rows_affected=1 (hold created).
  Seat Service: publish event: {seat_id, user_id, hold_id, event: SEAT_HELD}

Step 2: Charge payment.
  Order Service: consume SEAT_HELD event.
  Order Service: call Payment Service with idempotency_key = hold_id.
  Payment Service: charge $150 to user's card.
  
  On success: Payment Service sends callback (webhook): {hold_id, status: CHARGED, payment_ref: ref123}
  Order Service: publish event: {hold_id, event: PAYMENT_CHARGED}
  
  On failure: callback: {hold_id, status: CHARGE_FAILED}
  Order Service: publish event: {hold_id, event: PAYMENT_FAILED}

Step 3a: Payment success -> Confirm ticket.
  Seat Service: consume PAYMENT_CHARGED.
  UPDATE seats SET status='SOLD', order_id=...
  WHERE seat_id=... AND held_by=user_id AND hold_expires > NOW()
  
  Check: rows_affected=1 -> seat confirmed.
  Check: rows_affected=0 -> hold expired during payment (race condition).
    Compensate: refund the payment (publish PAYMENT_REFUND_REQUESTED event).
  
  Publish: TICKET_ISSUED event -> Notification Service sends email + ticket PDF.

Step 3b: Payment failure -> Release hold.
  Seat Service: consume PAYMENT_FAILED.
  UPDATE seats SET status='AVAILABLE', held_by=NULL, hold_expires=NULL
  WHERE seat_id=... AND held_by=user_id
  
  Hold released. User notified: "Payment failed. Your seat hold has been released."
  User must start over (re-join queue or select a different seat).

Idempotency for payment:
  Order Service calls Payment Service with idempotency_key = hold_id.
  If the user retries (double-click "purchase"), the same hold_id is used.
  Payment Service: "I already have a charge for this idempotency_key."
  Return: previous result. No double-charge.
```

---

## Failure Scenarios

### Failure 1: Redis queue service crashes during flash sale

```
Impact: position counter lost. New users cannot get queue positions.
  Users who already have positions: their position stored in Redis user key.
  If their key is also lost: they lose their place in line.

Recovery:
  Redis restarts from RDB snapshot (last 5 minutes).
  Position counter: resumes from the last known value (some positions may be re-issued).
  
  Re-issued positions: two users might have the same position number.
  Fix: position counter is never the only identifier. Entry token is generated
  from position + user_id + timestamp — unique per user.
  Even if two users have the same position number, their entry tokens are different.
  
  Users who lost their queue position: must rejoin. Frustrating but correct.
  The queue state is semi-durable (Redis with persistence + failover within 30s).
  A 30-second Redis outage during the sale affects users who arrived in that window.

Prevention:
  Redis persistence: RDB every 1 minute + AOF for all queue writes.
  Redis replica: promote within 10 seconds. During failover (10s): queue joins queued in the API server.
  Position counter overflow to Postgres: after Redis recovers, reconcile the counter.
```

### Failure 2: Seat hold succeeds in DB but Redis cache not updated

```
Scenario: seat A12 held by user A (Postgres: HELD). Redis cache update fails (network hiccup).
  Redis: still shows A12 as AVAILABLE.
  User B: reads seat map from Redis, sees A12 as AVAILABLE.
  User B: tries to hold A12.
  Seat Service: UPDATE WHERE seat_id='A12' AND status='AVAILABLE' -> rows_affected=0.
  Seat Service: "seat unavailable." User B told it's taken.

Result: correct behavior! The DB is the source of truth.
  User B is correctly told A12 is taken.
  The Redis cache showed stale data, but the DB prevented the double-hold.
  Redis staleness is a display issue, not a correctness issue.

Fix: Redis cache TTL (30 seconds). Even if an individual cache update fails,
the cache expires and is refreshed from DB within 30 seconds.
User B sees A12 as green on the seat map for up to 30 seconds, then it turns red.
This is acceptable — the correctness guarantee is in the DB.
```

### Failure 3: Payment webhook arrives after hold expires

```
Timeline:
  T=0:   User holds seat A12 (hold_expires = T+10min)
  T=9:55 User submits payment.
  T=10:05 Hold expires. Background job releases A12. A12 is now AVAILABLE.
  T=10:10 Payment service webhook arrives: PAYMENT_CHARGED.
  T=10:10 Order Service: UPDATE seats SET status='SOLD' WHERE held_by=user_A AND hold_expires > NOW()
           hold_expires was at T=10min. NOW() = T+10:10. hold_expires < NOW(). 0 rows updated.
  
  Seat A12 is now AVAILABLE (released by expiry job) and the user has been charged $150.

Mitigation:
  Order Service: on rows_affected=0 at confirm step:
  1. Check: is the seat now AVAILABLE or SOLD to someone else?
     If AVAILABLE: re-acquire the seat (UPDATE WHERE status='AVAILABLE').
     If successful: ticket issued. (Rare but benign: seat was briefly freed but we re-grabbed it.)
     
  2. If SOLD to someone else: the seat is gone.
     Trigger: PAYMENT_REFUND_REQUESTED for the $150 charged.
     Notify user: "Unfortunately your seat was released during payment processing. You have been refunded."
  
  The 10-second grace window between payment submission and hold expiry is the risk zone.
  Reduce risk: start the payment process at T+8min (warn user at 8 minutes remaining).
  Show countdown: "Only 2 minutes left! Pay now."
  
  If payment submission is at T+9min: 1-minute window for payment processing.
  Most payments complete in < 30 seconds. Risk: edge cases where payment takes > 60 seconds.
```

### Failure 4: Background hold-release job falls behind

```
Scenario: 600,000 holds currently in HELD status.
  Background job runs every 30 seconds.
  Each run: scans for expired holds. If job takes 45 seconds to run: next run starts while the previous is still running.
  Two concurrent runs: both try to UPDATE the same expired hold rows.
  Double-update: not a correctness issue (status is already set to AVAILABLE by the first run).
  But: extra DB load from concurrent scans.

Fix:
  Add a distributed lock on the expiry job:
    SET expiry_job_lock:event_{event_id} 1 NX EX 60
    (Only one instance can run the expiry job for this event at a time.)
  If lock cannot be acquired: skip this run.
  Lock expires after 60 seconds even if the job crashes.
  
  Performance: use a partial index on seats (status, hold_expires) for fast expired hold detection.
    CREATE INDEX ON seats (hold_expires) WHERE status = 'HELD'
    This index only contains rows where status='HELD'. Scans only relevant rows.
    At 600K HELD rows: full scan of index once every 30 seconds. Acceptable.
```

---

## API Design

### Hold Seats

```
POST /v1/events/{event_id}/holds
Request:  { seat_ids: [string], user_id: string,
            idempotency_key: string }           -- client-generated UUID
Response: { hold_id: string, seat_ids: [string], expires_at: timestamp,
            status: HELD }
Errors:   409 seat already held/sold, 400 seat_ids empty or >10,
          429 rate limited (CAPTCHA required)
Notes:    atomic UPDATE WHERE status='AVAILABLE'; rows_affected check
```

**Why idempotency_key on the hold request, not just on the payment:**
The client generates a UUID before the user clicks "hold." If the POST times out
and the user clicks again, the server uses the idempotency_key to detect the
duplicate and return the existing hold rather than creating a second hold that
consumes more of the user's 4-ticket limit. This is belt-and-suspenders on top
of the `ON CONFLICT (idempotency_key) DO NOTHING` constraint in the holds table.

**Why limit seat_ids to 10 per request:**
Anti-scalping policy. A user who needs more than 10 seats is almost certainly a
bot or a corporate buyer who should use a different purchase flow. Enforced at
the API layer before any DB write occurs.

---

### Confirm Purchase

```
POST /v1/holds/{hold_id}/purchase
Request:  { payment_method_id: string, user_id: string }
Response: { order_id: string, ticket_ids: [string], total_cents: int,
            confirmation_code: string }
Errors:   404 hold expired, 402 payment failed, 409 duplicate purchase
Notes:    Saga: hold -> charge -> confirm; compensating txn releases hold on failure
```

**Why 404 (not 410) for expired hold:**
The 410 Gone status is semantically correct but requires the client to handle an
extra error code. Ticketing SDKs universally use 404 for "hold not found or
expired" — the client UI message is "your hold has expired, please select a new
seat." The hold record is retained in the DB for 24 hours (for audit), but the
API treats it as not found once hold_expires < NOW().

**Saga sequence for this endpoint:**
```
1. Validate hold: SELECT FROM holds WHERE hold_id=? AND hold_expires > NOW() AND status='ACTIVE'
   -- If not found: 404
2. Call Payment Service: POST /charges {amount, payment_method_id, idempotency_key=hold_id}
   -- If declined: 402; compensating txn: UPDATE holds SET status='PAYMENT_FAILED'
3. Confirm seats: UPDATE seats SET status='SOLD' WHERE seat_id IN (hold.seat_ids) AND held_by=hold_id
   -- rows_affected must equal len(hold.seat_ids); if 0: hold expired during payment -> refund
4. Create order + tickets: INSERT INTO orders ...; INSERT INTO tickets ...
5. Publish order-confirmed event to Kafka (triggers email + barcode generation)
```

---

### Release Hold

```
DELETE /v1/holds/{hold_id}
Request:  { user_id: string }
Response: 204 No Content
Notes:    also triggered by background expiry job (partial index on hold_expires)
```

**Why DELETE and not POST /holds/{hold_id}/release:**
REST semantics: DELETE on a resource represents removal of that resource. A hold
is deleted (released) by the user or by the system. Using DELETE makes it
idempotent by convention: a DELETE on an already-released hold returns 204
without error, since the end state (seat available) is achieved regardless.

---

### Get Event Seat Map

```
GET /v1/events/{event_id}/seatmap
Response: { sections: [{section_id, name, seats: [{seat_id, row, number,
            status: AVAILABLE|HELD|SOLD, price_cents}]}] }
Notes:    status HELD shows as UNAVAILABLE to other users (privacy); cached 5s
```

**Why HELD shows as UNAVAILABLE (not HELD) to other users:**
Privacy. A seat in HELD state reveals that someone is actively purchasing. This
is fine. But the barcode-level hold_id is never exposed. More importantly, if the
API returned "HELD by user_abc at 10:23:42," that reveals purchasing behavior.
The public API collapses HELD and SOLD into a single UNAVAILABLE status. Only
internal admin APIs see the granular HELD status with hold owner and expiry.

**Caching strategy for this endpoint:**
```
Layer 1: Redis HGETALL event:{event_id}:seats -> all seat statuses (single round trip, ~70KB)
          TTL: 5 seconds. Updated on every status change (AVAILABLE -> HELD -> SOLD).
Layer 2: CDN cache (CloudFront) with 5s TTL and stale-while-revalidate for the GET response.
          This handles 10,000 users all hitting seatmap at T=0 without any backend.
Layer 3: WebSocket differential updates after initial load (only changed seat IDs pushed).
```

---

### Get Order / Ticket

```
GET /v1/orders/{order_id}
Response: { order_id, tickets: [{ticket_id, seat_id, barcode_payload: string,
            event_name, date, venue}] }
Notes:    barcode_payload = base64(seat_id + event_id + timestamp + HMAC-SHA256)
```

**Barcode payload construction:**
The barcode payload is generated at ticket creation (when the order is confirmed)
and stored in the tickets table as barcode_hmac. It is never regenerated on read
-- the stored value is returned directly. This means the gate scanner can verify
the barcode offline using the pre-loaded server secret key, without a network
call. The barcode_payload column stores the full base64-encoded signed blob; the
gate scanner decodes it, verifies the HMAC, and checks the event_date field
against today's date.

---

### API Design Summary Table

```
+---------------------------+--------+-------------------------------------------+
| Endpoint                  | Method | Idempotent? | Cached? | DB writes/call    |
+---------------------------+--------+-------------+---------+-------------------+
| /events/{id}/holds        | POST   | YES (idem   | NO      | 1 UPDATE + 1 INS  |
|                           |        | key)        |         | (seats + holds)   |
+---------------------------+--------+-------------+---------+-------------------+
| /holds/{id}/purchase      | POST   | YES (hold   | NO      | 1 UPDATE + 2 INS  |
|                           |        | id = idem)  |         | (seats,orders,    |
|                           |        |             |         |  tickets)         |
+---------------------------+--------+-------------+---------+-------------------+
| /holds/{id}               | DELETE | YES         | NO      | 1 UPDATE (seats)  |
+---------------------------+--------+-------------+---------+-------------------+
| /events/{id}/seatmap      | GET    | YES         | YES (5s)| 0 (Redis cache)   |
+---------------------------+--------+-------------+---------+-------------------+
| /orders/{id}              | GET    | YES         | YES     | 0 (read replica)  |
+---------------------------+--------+-------------+---------+-------------------+
```

---

## DB Schema

```sql
CREATE TABLE events (
  event_id       UUID         PRIMARY KEY,
  name           TEXT         NOT NULL,
  venue_id       UUID         NOT NULL,
  event_date     TIMESTAMPTZ  NOT NULL,
  sale_start     TIMESTAMPTZ  NOT NULL,
  status         VARCHAR(20)  NOT NULL DEFAULT 'ON_SALE'
);

CREATE TABLE seats (
  seat_id        UUID         PRIMARY KEY,
  event_id       UUID         NOT NULL REFERENCES events(event_id),
  section        VARCHAR(50)  NOT NULL,
  row_label      VARCHAR(10)  NOT NULL,
  seat_number    INT          NOT NULL,
  price_cents    INT          NOT NULL,
  status         VARCHAR(20)  NOT NULL DEFAULT 'AVAILABLE',
                                       -- AVAILABLE|HELD|SOLD
  hold_id        UUID,                 -- null unless HELD
  hold_expires   TIMESTAMPTZ,          -- null unless HELD
  UNIQUE (event_id, section, row_label, seat_number)
);
CREATE INDEX idx_seats_event_status ON seats(event_id, status);
-- Partial index for expiry background job (only scans HELD rows)
CREATE INDEX idx_seats_expiry ON seats(hold_expires)
  WHERE status = 'HELD';

CREATE TABLE holds (
  hold_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID         NOT NULL,
  event_id       UUID         NOT NULL,
  idempotency_key VARCHAR(64) UNIQUE NOT NULL,
  status         VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE|EXPIRED|PURCHASED
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  expires_at     TIMESTAMPTZ  NOT NULL
);

CREATE TABLE orders (
  order_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID         NOT NULL,
  hold_id        UUID         NOT NULL UNIQUE REFERENCES holds(hold_id),
  total_cents    INT          NOT NULL,
  payment_intent_id TEXT      NOT NULL,  -- Stripe PaymentIntent ID
  status         VARCHAR(20)  NOT NULL,  -- PENDING|CONFIRMED|REFUNDED
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE tickets (
  ticket_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id       UUID         NOT NULL REFERENCES orders(order_id),
  seat_id        UUID         NOT NULL UNIQUE REFERENCES seats(seat_id),
  barcode_hmac   TEXT         NOT NULL,  -- HMAC-SHA256 for offline gate scan
  is_transferred BOOLEAN      NOT NULL DEFAULT false
);
```

### Schema Design Decisions

**Why `hold_id` lives on the `seats` row (not just in the `holds` table):**
The atomic hold UPDATE needs to stamp the seats row with the hold that owns it.
This enables the Saga's confirm step to verify the correct hold is still active:
`UPDATE seats SET status='SOLD' WHERE seat_id=? AND hold_id=? AND status='HELD'`.
Without `hold_id` on the seats row, the confirm step would need a JOIN across
two tables inside a transaction -- more latency, more lock surface.

**Why `idempotency_key` has a UNIQUE constraint on the holds table:**
This is the server-side deduplication for duplicate POST /holds requests. If the
client sends the same idempotency_key twice, the second INSERT hits the UNIQUE
constraint and returns the existing hold_id. The application layer catches the
constraint violation and returns the original hold response instead of an error.
This is different from the payment-layer idempotency key -- both are needed.

**Why `hold_expires` is on the seats row AND the holds table:**
`seats.hold_expires`: used by the background expiry job index scan. The partial
index `WHERE status = 'HELD'` on `seats(hold_expires)` makes the expiry job O(expired_count)
not O(total_seats). Without this column on seats, the expiry job would need a
JOIN to the holds table for every HELD row -- much slower at scale.
`holds.expires_at`: used for API validation at purchase time. Two sources of
truth for the same expiry timestamp is intentional denormalization for performance.
They must be kept in sync (written in the same transaction when the hold is created).

**Why `orders.hold_id` has a UNIQUE constraint:**
Prevents double-purchase of the same hold. If the saga's confirm step runs twice
(due to Kafka consumer retry), the second INSERT INTO orders hits the UNIQUE
constraint and the saga detects "order already exists for this hold -- idempotent
success, return existing order_id." Without this, a retry creates two order rows
and charges the user twice.

**Why `tickets.seat_id` has a UNIQUE constraint:**
The hard invariant: one ticket per seat per event. This is the database-level
enforcement of the no-overselling guarantee, acting as a belt-and-suspenders
backup to the atomic UPDATE WHERE rows_affected=1 check. Even if a bug in the
application layer bypasses the atomic hold check, the DB will reject any INSERT
that tries to create a second ticket for the same seat.

### Index Strategy and Query Plans

```
Query: hold expiry background job (runs every 30 seconds)
  UPDATE seats SET status='AVAILABLE', hold_id=NULL, hold_expires=NULL
  WHERE status='HELD' AND hold_expires < NOW()
  
  Uses: idx_seats_expiry (partial index on hold_expires WHERE status='HELD')
  Rows scanned: only HELD rows with expired timestamps
  At 1,000 holds/sec, 10-min TTL: ~600,000 HELD rows max
  Expired per run (30s window): ~30,000 rows
  Index scan + update: O(expired_count) not O(total_seats)

Query: seat map load for one event
  SELECT seat_id, section, row_label, seat_number, status, price_cents
  FROM seats WHERE event_id = ?
  
  Uses: idx_seats_event_status (index on event_id, status)
  Rows returned: up to 70,000 (full stadium)
  Served from Redis cache 99%+ of the time -- DB query is cold-start fallback

Query: atomic hold for a single seat
  UPDATE seats SET status='HELD', hold_id=?, hold_expires=?
  WHERE seat_id=? AND status='AVAILABLE'
  
  Uses: PRIMARY KEY index (seat_id lookup, O(1))
  Row-level lock acquired and released in < 5ms under normal conditions
  Lock contention visible in pg_stat_activity if > 100 concurrent holds on same seat

Query: confirm purchase (saga step 3)
  UPDATE seats SET status='SOLD', hold_id=NULL
  WHERE seat_id = ANY(?) AND hold_id=? AND status='HELD'
  
  Uses: PRIMARY KEY index per seat_id
  Rows affected must == number of seats in hold; if 0, hold expired -> trigger refund
```

---

## Deep Concept Explanations

### Concept 1: Why SQL Row-Level Locking Works

```
When you issue:
  UPDATE seats SET status='HELD' WHERE seat_id='A12' AND status='AVAILABLE'

Postgres execution:
  1. Parse and plan the query.
  2. Scan: find the row for seat_id='A12' (index lookup, O(log N)).
  3. Acquire an exclusive row lock on this row.
     This lock prevents ANY other transaction from reading or modifying this row
     until our transaction commits or rolls back.
  4. Re-read the row under the lock (to get the current value).
  5. Evaluate WHERE status='AVAILABLE': is it still true?
     If yes: update status to 'HELD'. Commit.
     If no (another transaction changed it before we got the lock): WHERE is false. 0 rows updated.
  6. Release the lock on commit.

Concurrent scenario (both transactions execute at the same moment):
  T1 and T2 both try to hold seat A12.
  T1 acquires the row lock first (first to reach step 3).
  T2 tries to acquire the row lock -> BLOCKED (waits for T1 to commit).
  T1: status='AVAILABLE', updates to 'HELD', commits. Lock released.
  T2: acquires lock. Re-reads: status='HELD'. WHERE status='AVAILABLE' -> FALSE. 0 rows updated.
  T1: gets the seat. T2: does not.

Zero race conditions. This is how all databases implement "compare-and-swap" semantics.
```

### Concept 2: General Admission (Counter-Based) vs. Assigned Seating

```
For festivals, standing concerts, or any unassigned event:
  No seat_id. Just a count: "1000 tickets remaining."

Atomic decrement:
  UPDATE events SET tickets_remaining = tickets_remaining - 1
  WHERE event_id = ? AND tickets_remaining > 0
  RETURNING tickets_remaining
  
  rows_affected = 1 and returned value >= 0: success. User gets a ticket.
  rows_affected = 0: sold out.
  
  This is much simpler than assigned seating:
    One row to update instead of 60,000 rows.
    No seat map complexity.
    No "which seat" choice.
  
  At extreme scale (100K simultaneous decrements):
    100K concurrent UPDATEs on the same row = row-level lock contention.
    Only one transaction can update the row at a time.
    The other 99,999 are queued. If each takes 5ms: 99,999 * 5ms = 500 seconds of queue.
    The virtual queue prevents this: spread the 100K updates over minutes.

For hybrid (general admission with capacity per section):
  One counter per section (10 sections). Lock contention spread across 10 rows.
  10x throughput improvement vs. single counter.
```

### Concept 3: Idempotency Key Design

```
User submits payment. Their browser connection drops. They retry.
Without idempotency: charge $150 twice.
With idempotency key: charge $150 once.

Key design:
  idempotency_key = {hold_id}  (unique per hold, not per user)
  
  Why not user_id? A user may hold multiple seats for different events.
  Why not hold_id + attempt_number? The key must be stable across retries.
  
  Order Service sends to Payment Service:
  {
    idempotency_key: "hold_abc123",
    amount: 15000,  // $150.00 in cents
    currency: "USD",
    card_token: "tok_xyz"
  }
  
  Payment Service (Stripe/Braintree):
    On first request with this key: process payment, store result.
    On second request with same key: return stored result (no re-processing).
  
  Storage: Payment Service keeps a KV store of {idempotency_key -> result} with 24h TTL.
  Any retry within 24 hours gets the same result as the first call.
  
  What if the first call's result is "DECLINED"?
  Idempotency key stores "DECLINED" result.
  Second retry: same "DECLINED" returned.
  User must use a different card (new hold_id if they re-select the seat, or same hold_id with new card token).
  This is correct: we do not want to silently retry a declined card.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+-----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)              | L6 (Staff)                     |
+---------------------+-----------------------------+--------------------------------+
| Atomic hold         | Correct: UPDATE WHERE       | Explains row-level lock        |
|                     | status='AVAILABLE', check   | mechanics. Multi-seat batch    |
|                     | rows_affected               | hold with deadlock prevention  |
|                     |                             | (sorted order acquisition).    |
+---------------------+-----------------------------+--------------------------------+
| Hold expiry         | Background job every 30s    | Partial index for fast scan.   |
|                     | UPDATE WHERE hold_expires   | Distributed lock on job.       |
|                     | < NOW()                     | Grace period for payment       |
|                     |                             | webhook arrival after expiry.  |
+---------------------+-----------------------------+--------------------------------+
| Virtual queue       | Redis INCR, release rate,   | Randomized within time windows |
|                     | entry token                  | (fairness). Bot detection:     |
|                     |                             | IP rate limit + CAPTCHA +      |
|                     |                             | account age. Queue abandonment:|
|                     |                             | users who join but don't       |
|                     |                             | complete within 15m = skip.    |
+---------------------+-----------------------------+--------------------------------+
| Saga pattern        | Hold -> pay -> confirm.     | Exactly: the hold-expired-     |
|                     | On payment fail: release    | during-payment race. Re-       |
|                     | hold.                       | acquire if still available.    |
|                     |                             | Refund if not. Idempotency     |
|                     |                             | key scoped to hold_id not      |
|                     |                             | user_id.                       |
+---------------------+-----------------------------+--------------------------------+
| Seat map display    | Redis cache + WebSocket     | HGETALL for 60K seats: 3MB     |
|                     | updates                     | response. Paginate by section  |
|                     |                             | for large venues. TTL vs.      |
|                     |                             | event-driven invalidation      |
|                     |                             | trade-off.                     |
+---------------------+-----------------------------+--------------------------------+
| Multi-region        | Not addressed               | Partition inventory: US gets   |
|                     |                             | 30K seats, EU gets 30K.        |
|                     |                             | Cross-region hold not needed   |
|                     |                             | (buyers in each region compete |
|                     |                             | for their regional inventory). |
|                     |                             | Prevents cross-region DB lock  |
|                     |                             | contention.                    |
+---------------------+-----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Ticketmaster Taylor Swift Onsale Failure (2022)

**Company:** Ticketmaster  
**What happened:** The Taylor Swift "Eras Tour" onsale generated 14 million queue participants — 4x Ticketmaster's previous record. Ticketmaster's virtual queue system (TM+ Verified Fan) was overwhelmed. Queue position estimates were wildly inaccurate (users shown "30 minute wait" waited 5+ hours). Many users were dropped from the queue when their session expired. Others who reached the front of the queue experienced error pages when attempting to complete purchases. Bot traffic that bypassed the queue consumed a significant portion of inventory before human buyers could reach checkout. Ticketmaster ultimately cancelled the general public onsale.

**Root cause (publicly reported):** Session management overload — Ticketmaster's system maintained session state for all queued users, and the sheer volume exceeded their session storage capacity. Additionally, the CAPTCHA and bot-detection systems slowed human users more than they slowed bots (bots had pre-solved CAPTCHA farms).

**Lessons:**
- Queue system must be stateless: position tokens (JWTs with signed position numbers) instead of server-side session storage for queue state
- Bot detection via CAPTCHA is arms-race that bots often win; behavioral analysis (mouse movements, typing patterns) is more effective
- Load test at 4x expected record volume, not just 1.5x

---

### Incident 2: Coachella Double-Seated Ticketing Error (2019)

**Company:** Coachella (via Ticketmaster)  
**What happened:** A database migration to a new ticketing system was performed during a low-traffic period. The migration had an off-by-one error in the seat status synchronization: 2,000 seats that were marked SOLD in the old system were migrated as AVAILABLE in the new system. When those 2,000 seats were shown as available and purchased, Coachella had 2,000 "ghost seats" — confirmed tickets for non-existent inventory. 2,000 customers arrived with valid tickets for seats already occupied. Coachella upgraded those customers to general admission (and issued refunds), at significant cost.

**Root cause:** Migration logic compared seat IDs but did not verify count integrity. Old system: 70,000 SOLD seats. New system after migration: 68,000 SOLD. The 2,000 gap was not caught by a post-migration integrity check.

**Fix:** Post-migration invariant checks: total SOLD count in new system must equal total SOLD count in old system. Row-by-row validation: for each SOLD seat in old system, verify it is SOLD in new system. Run integrity check before going live on the new system.

**Staff lesson:** Database migrations for inventory systems must include count-level and row-level integrity verification. "Does the total add up?" is the minimum. "Does each specific item match?" is the correctness guarantee.

---

### Incident 3: Stubhub Hold Expiry Race Condition (2020)

**Company:** StubHub  
**What happened:** StubHub's hold expiry job ran every 60 seconds. The job released 10,000 expired holds per run. Simultaneously, a new batch of users was being let through the queue and attempting to hold those same seats. The release job and the new hold attempts hit the same rows simultaneously. In 12 cases, the UPDATE to release (status='AVAILABLE') executed after the UPDATE to hold (status='HELD') for the same seat, setting the held seat back to AVAILABLE. Those 12 seats were sold to two users each (the holder and the user who held it after the false release).

**Root cause:** The expiry job's UPDATE did not check the held_by or hold_expires carefully enough:
  `UPDATE seats SET status='AVAILABLE' WHERE status='HELD' AND hold_expires < NOW()`
  A seat held at T=10:00:05 with hold_expires=T+10min was released at T=10:00:10 if the expiry job ran slightly before T=10:00:05.
  
Actually: clock skew between the DB server (recording hold_expires) and the application server (computing NOW() for the release job) caused the expiry job to release holds that were set by the application server's clock but were not yet expired from the DB server's perspective.

**Fix:** Added a 30-second buffer to the expiry check: `WHERE status='HELD' AND hold_expires < NOW() - INTERVAL '30 seconds'`. This ensures that a hold is not released until it has been expired for at least 30 seconds. Small cost: users may wait up to 30 extra seconds for a released seat to become available. Large benefit: eliminates the clock-skew race condition.

**Staff lesson:** Distributed systems have clock skew. Any "expires at timestamp" check must include a buffer. The cost of releasing a hold 30 seconds late is trivially small; the cost of releasing an active hold is a double-sell.

---

## Exercises

### Exercise 1: Atomic Hold SQL

**Problem:** Write the SQL statement to atomically hold seat 'A-12' for user 'user_abc' in an event 'event_456'. The hold should expire in 10 minutes. The seat table has columns: seat_id, event_id, status (AVAILABLE/HELD/SOLD), held_by, hold_expires. How do you check if the hold succeeded?

**Solution:**

```sql
UPDATE seats
SET
  status       = 'HELD',
  held_by      = 'user_abc',
  hold_expires = NOW() + INTERVAL '10 minutes'
WHERE
  seat_id  = 'A-12'
  AND event_id = 'event_456'
  AND status   = 'AVAILABLE';

-- Check success:
-- affected_rows = 1 -> success. Seat is held. Return hold details to user.
-- affected_rows = 0 -> failure. Seat is HELD or SOLD. Return "seat unavailable."

-- In Python (psycopg2):
cursor.execute("""
  UPDATE seats SET status='HELD', held_by=%s, hold_expires=NOW()+INTERVAL '10 minutes'
  WHERE seat_id=%s AND event_id=%s AND status='AVAILABLE'
""", ('user_abc', 'A-12', 'event_456'))
success = cursor.rowcount == 1  # rowcount = rows affected by the UPDATE

-- In Java (JDBC):
int affected = preparedStatement.executeUpdate();
boolean success = (affected == 1);

-- Why NOT check with a SELECT first:
-- Wrong: SELECT status FROM seats WHERE seat_id='A-12' -> 'AVAILABLE' -> then UPDATE
-- The SELECT and UPDATE are two separate statements. Another user can UPDATE between them.
-- The WHERE status='AVAILABLE' in the UPDATE IS the check. They are one atomic operation.
```

---

### Exercise 2: Queue Math

**Problem:** A concert goes on sale with 50,000 seats. 8 million users join the queue at T=0. The queue releases 500 users per second into the seat selection. Assume 40% of users who enter seat selection complete a purchase. How long until all seats are sold? How many users in the queue never get to purchase?

**Solution:**

```
Users entering seat selection per second: 500
Users completing purchase per second: 500 * 40% = 200 purchases/sec
Time to sell all 50,000 seats: 50,000 / 200 = 250 seconds = 4 minutes 10 seconds

Users who enter seat selection during the 250-second sale period:
  500 users/sec * 250 sec = 125,000 users enter selection
  Of these: 50,000 complete purchases, 75,000 don't (seats run out or they abandon)

Queue exhaustion:
  All seats sold after 250 seconds.
  Users who entered the queue but have not reached seat selection by T+250s:
    8,000,000 total users - 125,000 who entered selection = 7,875,000 users who never get in.
  Of the 125,000 who entered: 75,000 got to browse but found no seats.
  
  Effectively: 7,875,000 out of 8,000,000 users (98.4%) never get to purchase.
  This is realistic: Eras Tour had ~4,000,000 users queue for 70,000 seats.
  
  At queue position 125,001: users should immediately be notified "sold out" instead of waiting.
  Implementation: when seats_remaining = 0, set queue:{event_id}:sold_out = 1 EX 3600.
  Queue Service: check sold_out flag on each status poll. If set: show "event sold out."
  
  Estimated wait time formula:
    wait = max(0, (user_position - current_release_position) / release_rate)
    wait = max(0, (4,000,000 - current_position_released) / 500)
    For user at position 500,000: wait = (500,000 - 0) / 500 = 1,000 seconds = 16 minutes.
    They would enter selection before the 250-second sell-out. They have a chance.
    For user at position 200,000: wait = 400 seconds. Enter at T+400s. Seats sold at T+250s. No chance.
```

---

## Homework

**Short 1:** Next time a high-demand concert or event goes on sale (set up Google alerts for events you like), observe the queue system. Note: (a) What position number are you assigned? (b) Does the estimated wait time update in real time? (c) How does the UI handle when seats sell out before you reach the front?

**Short 2:** Look at Postgres documentation for `UPDATE ... RETURNING`. How does RETURNING work? Write a SQL statement that holds a seat AND returns the new hold_expires timestamp in a single statement (without a separate SELECT after the UPDATE).

**Short 3:** Research the Taylor Swift Ticketmaster failure of 2022. What specific technical failures did Ticketmaster acknowledge? How did Ticketmaster's Verified Fan system attempt to prevent bots, and why did it fail at this scale?

**Deep:** Implement a mini ticketing system:
- Create a Postgres `seats` table with 1,000 seats, all AVAILABLE.
- Write a Python script that simulates 100 concurrent users all trying to hold seat 'A-1' simultaneously (use threading or asyncio).
- Run the script WITHOUT the atomic UPDATE (use SELECT then INSERT) and count how many "successful" holds you get. Should be > 1 (race condition demonstrated).
- Fix with the atomic UPDATE WHERE status='AVAILABLE'. Run again. Should always get exactly 1 success.
- Add the hold expiry: a background thread that scans for holds older than 10 seconds and releases them.

---

## Glossary

**Seat hold:** A temporary reservation (typically 10 minutes) that marks a seat as unavailable to other buyers while the reserving user completes payment. Implemented as an atomic UPDATE to prevent race conditions.

**Atomic compare-and-swap (CAS):** An operation that reads a value, checks it against an expected value, and only writes a new value if the check passes — all as a single indivisible operation. In SQL: `UPDATE WHERE column='expected' AND SET column='new'`. Zero race conditions between the check and the update.

**rows_affected:** The count of rows modified by a DML statement (UPDATE, INSERT, DELETE). After an atomic seat hold UPDATE, rows_affected=1 means success (the seat was available and is now held); rows_affected=0 means failure (the seat was already held or sold).

**Virtual queue (waiting room):** A system that issues numbered positions to users during a flash sale and releases them into the sale at a controlled rate, preventing the database from being overwhelmed. Implemented via a Redis INCR counter and a rate-limited release mechanism.

**Hold expiry:** The automatic release of a seat hold after the hold duration expires (typically 10 minutes). Implemented as a background job that scans for holds with `hold_expires < NOW()` and resets their status to AVAILABLE.

**Saga pattern:** An approach to distributed transactions that uses a sequence of local transactions, each publishing events, with compensating transactions to undo partial work on failure. For ticketing: hold seat → charge payment → confirm ticket; on failure at any step, compensating actions undo prior steps.

**Compensating transaction:** An action that reverses the effect of a previously completed step in a saga. For ticketing: if payment fails after a seat is held, the compensating transaction is releasing the hold (setting seat status back to AVAILABLE).

**Idempotency key:** A unique identifier sent with each request to ensure that retrying the same request does not cause duplicate effects. For ticketing: the hold_id serves as the payment idempotency key, ensuring that retrying a payment for the same hold never charges the user twice.

**General admission:** An event format without assigned seats — buyers purchase a ticket to enter (no specific seat number). Simpler inventory model: one atomic decrement of a counter instead of per-seat row locks.

**Two-phase hold:** The pattern of first holding a seat (AVAILABLE → HELD) and then confirming (HELD → SOLD) after payment success. The hold provides the user time to complete payment without the seat being sold to someone else.

---

## The One-Sentence Summary

> "Ticketing = atomic seat hold (`UPDATE seats WHERE status='AVAILABLE'`, check rows_affected=1 to prevent overselling) + 10-minute hold expiry (background job releases abandoned holds) + virtual waiting room (Redis INCR queue + rate-limited 1,000 users/sec release to control DB load at T=0 flash sale) + saga pattern (hold → payment → confirm with compensating release on payment failure) — the entire correctness of the system rests on one invariant: checking availability and claiming the seat must be a single atomic database operation, never two separate steps."

---

## Interview Q&A — Most Common Cross-Questions

---

**Q1: How do you prevent two users from buying the same seat?**

The key is making the availability check and the reservation a single atomic operation in the database. The wrong approach reads availability in one query and then writes the reservation in a separate query — another user can slip between those two steps. The correct approach is a single UPDATE statement: `UPDATE seats SET status='HELD' WHERE seat_id='A12' AND status='AVAILABLE'`. The database's row-level locking ensures only one transaction can execute this update on row A12 at a time. The first transaction succeeds and sets status to HELD. The second transaction runs after the first commits, finds status='HELD' (not AVAILABLE), and gets rows_affected=0. Only one user gets the seat.

---

**Q2: What is the virtual queue and why is it necessary?**

Without a queue, at the moment a sale opens, millions of users simultaneously hit the hold_seat endpoint. Even if the database can handle high write volume, the sudden spike (14 million in one minute) saturates connection pools, causes timeouts, and cascades into retries that amplify the load. A virtual queue assigns each arriving user a position number (via a Redis INCR counter) and only allows a controlled rate — say, 1,000 users per second — to proceed to seat selection. From the database's perspective, it sees a steady 1,000 hold attempts per second instead of a 14-million-per-minute spike. This trades user waiting time for system stability, and the tradeoff is correct: the alternative is the system crashing for everyone.

---

**Q3: What happens if a user holds a seat but their browser crashes before they pay?**

The hold has an expiry timestamp (10 minutes from creation). A background job runs every 30 seconds and executes: `UPDATE seats SET status='AVAILABLE' WHERE status='HELD' AND hold_expires < NOW()`. The expired hold is released, the seat becomes available again, and the next user can hold it. Redis cache is invalidated: the seat turns green on browsing users' maps. The user whose browser crashed sees an error when they reconnect: "Your hold has expired. Please select a new seat." The 10-minute window is intentionally short to prevent seats from being locked by idle or abandoned sessions.

---

**Q4: What happens if the payment succeeds but the ticket confirmation fails?**

This is the partial saga failure case. The payment service has charged the user's card ($150 debited). But the Order Service's step to mark the seat SOLD has failed (DB timeout, service crash, etc.). The user is charged but has no ticket. Recovery: the saga detects the confirmation failure (no TICKET_ISSUED event within 30 seconds of PAYMENT_CHARGED). It triggers a compensating transaction: refund the payment, release the seat hold. Notification sent to the user: "We encountered an issue confirming your ticket. You have been refunded. Please try again." The hold is released and another user can purchase the seat. The idempotency key (hold_id) on the payment ensures that if the system retries the payment call, it gets "already charged" not a duplicate charge.

---

**Q5: How do you handle multiple seats — user wants 4 tickets together?**

Hold all four seats atomically or none. One approach: `UPDATE seats SET status='HELD' WHERE seat_id IN ('A12', 'A13', 'A14', 'A15') AND status='AVAILABLE'`. Check rows_affected=4; if fewer, undo the partial hold with another UPDATE to release the held seats. A cleaner approach uses SELECT FOR UPDATE to lock all four rows and then verify all are AVAILABLE before committing. To prevent deadlocks when two users race for overlapping seat sets (both want A13 and A14), always acquire row locks in sorted seat_id order. This canonical ordering prevents circular wait: both users will try to lock the alphabetically first seat first, so one blocks the other rather than deadlocking.

---

**Q6: How do you show the seat map with real-time availability to all browsing users?**

Seat status (AVAILABLE/HELD/SOLD) for all 60,000 seats is cached in Redis as a hash per event. This allows a single HGETALL to return all seat statuses in one round trip (~3 MB). When any seat status changes (hold, release, or sell), the Redis cache entry is updated immediately. Users browsing the seat map maintain a WebSocket connection. When a seat status changes, the WebSocket server pushes an update to all connected clients: "seat A12 is now HELD" — the user's seat map turns that seat red. Released seats turn green. This real-time feedback helps users see which seats are about to expire and become available again.

---

**Q7: How do you handle the T=0 traffic spike without crashing the server?**

Three layers. First, the API gateway rate-limits queue joins per IP to prevent bots from occupying all queue positions. Second, the virtual queue (Redis INCR counter) absorbs all queue joins in O(1) per user, keeping the queue join handler stateless and horizontally scalable. The queue join itself does not touch the seat database. Third, the rate-limited queue release (N users per second into seat selection) means the seat service database sees a controlled write rate regardless of how many users are in the queue. The database never sees the 14-million-user spike — it sees whatever rate we configure the queue to release at.

---

*Section 5 — L5 / Senior SWE. Frequently asked at ticketing companies, e-commerce (flash sales), and any marketplace with limited inventory. Pairs with Ch61d (Hotel Reservation) for similar hold patterns at smaller scale, and Ch58 (Payment Flow) for the payment saga.*

---

**Q8: How do you handle dynamic pricing — ticket prices that increase as seats sell out?**

The seats table stores both a `base_price` and a `current_price` per seat (or per section). A Pricing Engine runs every 5 minutes and checks the ratio of HELD+SOLD seats to total capacity per section. At 50% sold: price stays at base. At 70% sold: price increases by 10%. At 85% sold: +20%. At 95% sold: +30%. The current_price is written back to the DB. When a user requests a hold, the Order Service reads `current_price` at the moment of hold creation — not at browse time. If price changed between when the user browsed and when they hold, the API returns the new price and asks the user to confirm before proceeding. Never charge a price the user did not explicitly see and approve. The hold record stores the locked_price field so the payment step always charges exactly what was confirmed, even if the price changes again during the 10-minute hold window.

---

**Q9: How do you handle ticket transfer — selling or giving a ticket to another person?**

Ticket transfer has three steps: (1) the original holder initiates a transfer (specifying recipient email), (2) the recipient claims the ticket, (3) the original barcode is invalidated and a new barcode is issued. In the DB: create a new ticket record for the recipient (`INSERT INTO tickets ... status='PENDING_TRANSFER'`), mark the original as TRANSFERRED, and atomically swap barcodes. Barcode invalidation must propagate to the gate scanner system before the event. The transfer cutoff is typically 24 hours before event start — after that, the gate list is finalized and changes are rejected. For paid transfers (resale), the saga is: hold the transfer → collect payment from buyer → confirm transfer → refund original holder (minus platform fee). The key invariant: at no point should two valid barcodes exist for the same seat at the same event.

---

**Q10: How do you prevent scalper bots from buying all tickets in the first minute?**

Multi-layer defense:

Layer 1 — CAPTCHA at queue join: require reCAPTCHA v3 score > 0.7 before issuing a queue position. Score < 0.5 → challenge with image CAPTCHA. Bots using headless browsers score near 0 on reCAPTCHA v3 (which uses mouse movement, keyboard timing, and behavioral signals).

Layer 2 — Account verification: require phone number verification before participating in a presale. Bots need a unique phone per account. New accounts (< 7 days old) are routed to higher queue positions (longer wait).

Layer 3 — Hold fee deposit: charge a $2 deposit at hold creation, refundable on purchase completion, forfeit on hold abandonment. Holding 10,000 seats costs a bot $20,000. Dramatically changes the economics.

Layer 4 — Purchase limit enforcement: max 4 tickets per account per event. Stored as a unique constraint: `(user_id, event_id)` with a count check. A bot would need 2,500 accounts to buy out a 10,000-seat show.

Layer 5 — Device fingerprinting: at the frontend, collect browser fingerprint (canvas, WebGL, font enumeration). Same device fingerprint across multiple accounts → flag for manual review.

Layer 6 — Behavioral analysis: detect superhuman hold speed (hold placed within 2 seconds of sale open, before any human could navigate the seat map). Flag and delay those accounts.

---

**Q11: How do you audit every seat sale for regulatory compliance and fraud detection?**

Every state transition (AVAILABLE→HELD, HELD→SOLD, HELD→AVAILABLE on expiry, SOLD→REFUNDED) is published to a Kafka topic `seat_state_transitions` with: timestamp, seat_id, old_status, new_status, user_id, hold_id, event_id, IP address, device fingerprint. A separate Audit Service consumes this stream and writes to an immutable append-only audit log (AWS S3 + Glue for queryability, or a dedicated audit DB with no UPDATE/DELETE permissions). For fraud detection: the analytics pipeline checks for patterns like "same user bought from 12 different IPs in 10 minutes" or "high-value resale listings appearing within 2 minutes of purchase." The audit log is retained for 7 years (PCI-DSS requirement for card transaction records).

---

**Q12: How does the gate scanner validate a barcode in real time, and what if the scanner loses connectivity?**

The gate scanner calls a barcode validation API: `GET /barcodes/{barcode_id}/validate`. The backend checks: (1) does this barcode exist in the tickets DB? (2) is the ticket status=SOLD (not REFUNDED, TRANSFERRED, or DUPLICATE)? (3) is it the correct event and date? (4) has this barcode already been scanned today? The scan event is written immediately: `INSERT INTO barcode_scans (barcode_id, gate_id, scanned_at)`. Duplicate scan (same barcode scanned twice) returns a `DUPLICATE_ENTRY` error with the timestamp of the first scan.

Offline mode: if the scanner loses connectivity, it falls back to a local SQLite database pre-loaded with all valid barcodes for today's events (downloaded at start of shift). Offline scans are queued and synced when connectivity restores. Risk: a refunded or transferred ticket might still appear valid in the offline cache. Mitigation: download cache updates every 30 minutes; if a high-risk ticket (refunded in last 4 hours) is flagged, alert the gate supervisor even in offline mode.

---

**Q13: How do you design the seat map so 14 million users can browse availability without hammering the database?**

Three layers of caching:

Layer 1 — Redis hash: `HGETALL seat_map:{event_id}` returns all seat statuses as `{seat_id → status}`. This hash is the canonical in-memory state. The background job that updates seat statuses also updates this hash atomically (inside the same Postgres transaction's post-commit hook: `HSET seat_map:{event_id} A12 HELD`).

Layer 2 — CDN-cached seat map snapshot: every 10 seconds, a worker generates a compact binary encoding of the full seat map (70,000 seats × 2 bits each = 17.5 KB) and pushes it to the CDN with a 10-second TTL. Users who first load the seat map download this from CDN — no backend involved. This handles the initial load spike when 14M users hit the seat map simultaneously.

Layer 3 — WebSocket differential updates: after the initial map load, each user's browser opens a WebSocket connection. The seat map backend subscribes to the seat_state_transitions Kafka topic and pushes differential updates (`{seat_id: "A12", status: "HELD"}`) to all connected browsers in real time. Only changed seats are pushed — not the full 70,000-seat map.

---

**Q14: What happens when a seat hold expires while the user is entering payment details?**

The user has 10 minutes from hold creation. At T-2 minutes, the frontend sends a warning: "2 minutes remaining." At T-0, the background job releases the hold (HELD → AVAILABLE). If the user submits payment at T+30 seconds: the payment call arrives at the Order Service with a hold_id. The Order Service validates: `SELECT * FROM holds WHERE hold_id='H123' AND hold_expires > NOW()`. The hold_expires is in the past — the hold is expired. Return a 409 Conflict: "Your hold has expired. Please select a new seat." The user must restart from seat selection. The payment is not charged (the charge would be the next step, but we validate the hold first). If the user had entered card details, those are discarded server-side since no charge was initiated.

---

**Q15: How do you design inventory management for GA (general admission) events vs. assigned seating?**

GA is simpler: instead of per-seat rows, track a single counter per event and ticket tier:

```sql
CREATE TABLE ga_inventory (
  event_id    BIGINT,
  tier_id     BIGINT,         -- e.g., GA_FLOOR, GA_BALCONY
  total       INT,
  held        INT DEFAULT 0,
  sold        INT DEFAULT 0,
  PRIMARY KEY (event_id, tier_id)
);
```

To hold a GA ticket:
```sql
UPDATE ga_inventory
SET held = held + 1
WHERE event_id = ? AND tier_id = ? AND (sold + held) < total;
-- Check rows_affected = 1. 0 means sold out.
```

To release an expired GA hold:
```sql
UPDATE ga_inventory SET held = held - 1 WHERE event_id = ? AND tier_id = ?;
```

GA avoids all the complexity of per-seat row locking and seat map rendering. The tradeoff: no seat selection, no printed seat number, and the barcode is associated with a tier (e.g., "General Admission Floor") not a specific physical seat. For large GA events (festivals with 100,000 attendees): use atomic Redis INCR/DECR for the counter (faster than DB), with DB as source-of-truth reconciled every 60 seconds.

---

## Monitoring and Observability

### Key Metrics by Layer

**Hold pipeline:**

| Metric | Healthy Range | Alert Threshold |
|--------|--------------|-----------------|
| `hold_creation_rate` /sec | 0–5,000 | > 8,000 sustained (capacity limit) |
| `hold_success_rate` % | 80–99% | < 60% for > 2 min (not due to natural sell-out) |
| `hold_expiry_rate` /min | 100–2,000 | Sustained spike > 5,000 (indicates bot hold-and-abandon) |
| `seat_availability_%` per section | 0–100% | < 5% (section nearly sold out — alert pricing engine) |

**Payment funnel:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `payment_funnel_enter_rate` /min | > 80% of hold creators | < 50% (users abandoning checkout) |
| `payment_success_rate` % | > 85% | < 70% (payment gateway issue) |
| `saga_rollback_rate` /min | < 10 | > 50 (upstream failure cascading) |
| `saga_median_duration_ms` | < 3,000 | > 10,000 (payment gateway slow) |

**Virtual queue:**

| Metric | Description |
|--------|-------------|
| `queue_depth` | Current number of users waiting |
| `queue_drain_rate` /sec | Users being released (should equal configured N) |
| `queue_abandonment_rate` % | Users who left before release (> 30% = too long a wait) |
| `queue_p99_wait_min` | p99 wait time in minutes |

**Database:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `seat_hold_latency_p99_ms` | < 20ms | > 100ms (row lock contention) |
| `lock_wait_count` /sec | < 50 | > 500 (multi-seat holds causing deadlock chain) |
| `expiry_job_duration_ms` | < 20,000 | > 28,000 (falling behind, will miss 30s window) |
| `deadlock_count` | 0 | > 0 (multi-seat lock order bug) |

### Distributed Trace Structure

Every hold-pay-confirm saga is one trace with 6 spans:

```
Trace: hold_and_purchase (saga_id = hold_id)
  ├─ Span 1: api_gateway (POST /holds)         2ms
  ├─ Span 2: queue_check (Redis INCR)          1ms
  ├─ Span 3: seat_lock (Postgres UPDATE)       8ms   ← row lock contention shows here
  ├─ Span 4: hold_record_create (INSERT)       5ms
  ├─ Span 5: payment_call (Payment Service)    1,200ms  ← gateway latency shows here
  └─ Span 6: order_confirm (UPDATE+INSERT)     10ms
```

Tags on all spans: `user_id`, `event_id`, `seat_id`, `hold_id`, `saga_rollback=true/false`.
Alert on: p99 of Span 3 > 50ms (lock contention), p99 of Span 5 > 5,000ms (gateway degraded), saga_rollback=true rate > 5/min.

---

## Capacity Planning — Taylor Swift Eras Tour Scale

**Event:** 3-night stadium residency, 70,000 seats per night. Anticipated concurrent sale openers: 14 million users.

**T=0 queue join:**
```
14,000,000 users in first 120 seconds = 116,667 requests/sec
Each request: Redis INCR (sub-millisecond, Redis handles 500K ops/sec)
API tier: 116,667 RPS → each API pod handles ~300 RPS → need 390 pods
Connection spike: 14M users × 1 connection × 5-sec hold = 2.8M concurrent connections
API pods: 390 pods × 7,200 connections each (manageable with async I/O)
```

**Seat map browsing (while in queue):**
```
7M users browsing map (50% of queue) × 1 read/10 sec = 700,000 Redis reads/sec
Mitigation: 3 Redis read replicas → 233K reads/sec per replica (comfortable at ~50% capacity)
CDN pre-load: static seat map snapshot updated every 10 seconds → handles initial burst
```

**Controlled hold creation:**
```
Queue release rate: 1,000 users/sec (configured)
Hold attempts/sec: 1,000
Each hold: 1 atomic UPDATE on seats (row lock) + 1 INSERT on holds
Seat row locks: 1,000 concurrent → 1,000 row locks on 70,000 rows → very low contention (<2% of rows locked)
Multi-seat hold (4 seats): 4,000 row locks/sec, always sorted → negligible deadlock risk
```

**Database sizing:**
```
seats table:    70,000 rows × 200 bytes = 14 MB (fits entirely in Postgres buffer cache)
holds table:    peak 70,000 active holds × 300 bytes = 21 MB (rotates every 10 min)
orders table:   70,000 completed orders × 500 bytes = 35 MB
Total hot data: ~70 MB → 1 Postgres instance with 32 GB RAM, zero disk I/O needed
```

**WebSocket seat map updates:**
```
14M connected users × 200 bytes/update × 1 update/10 sec = 280 MB/sec bandwidth
280 MB/sec = 2.24 Gbps total WebSocket egress
WebSocket tier: 50 servers × 280,000 connections each at 1 Gbps/server = 50 Gbps total (adequate)
```

**Sale duration estimate:**
```
70,000 seats × avg 3 per order = 23,333 transactions needed
At 1,000 users/sec release × 70% hold rate = 700 holds/sec
At 80% payment conversion = 560 confirmed orders/sec
23,333 orders ÷ 560/sec = 41.7 minutes to sell out
Total queue time for last user: 14M ÷ 1,000/sec = 14,000 seconds = 233 minutes (→ show is sold out before last user is released)
```

---

## Common Anti-Patterns

**Anti-pattern 1: Two-query hold (check then update)**
```sql
-- WRONG: race condition between SELECT and UPDATE
SELECT status FROM seats WHERE seat_id = 'A12';  -- returns 'AVAILABLE'
-- another user grabs the seat here --
UPDATE seats SET status = 'HELD' WHERE seat_id = 'A12';  -- seat now held twice!
```
Fix: `UPDATE seats SET status='HELD' WHERE seat_id='A12' AND status='AVAILABLE'`. Check rows_affected=1.

**Anti-pattern 2: Holding before availability check**
```sql
-- WRONG: hold created in app layer, seat updated separately
hold = db.insert("INSERT INTO holds ...")
seat = db.update("UPDATE seats SET status='HELD' WHERE seat_id=?")
-- crash between these two → orphaned hold record with no matching seat status
```
Fix: Use a single transaction. The hold INSERT and seat UPDATE happen atomically or neither does.

**Anti-pattern 3: No idempotency key on payment**
```python
# WRONG: retry on network timeout → double charge
def confirm_payment(hold_id):
    charge_card(user_id, amount)  # may run twice on timeout retry!
```
Fix: `charge_card(user_id, amount, idempotency_key=hold_id)`. The payment provider deduplicates on this key — retries with the same key return the original result without re-charging.

**Anti-pattern 4: Releasing hold before payment confirmation**
```python
# WRONG: seat released before payment confirmed
release_hold(hold_id)         # seat AVAILABLE again -- race condition!
payment = charge_card(...)
if payment.success:
    mark_seat_sold(seat_id)   # another user may have grabbed the seat!
```
Fix: Hold must remain HELD throughout payment. Transition HELD→SOLD on payment success, HELD→AVAILABLE on failure. Never release a hold before knowing the payment outcome.

**Anti-pattern 5: Unbounded executor on payment gateway calls**
```java
// WRONG: unbounded thread pool + no timeout → OOM on gateway slowdown
ExecutorService pool = Executors.newCachedThreadPool();  // unbounded!
pool.submit(() -> paymentGateway.charge(order));  // hangs for 10 min on slow gateway
// 50,000 users → 50,000 threads → heap exhaustion
```
Fix: Bounded thread pool (max 500 threads) + short circuit breaker on payment gateway latency > 3,000ms. When circuit is open, return 503 "payment service temporarily unavailable" instead of hanging.

**Anti-pattern 6: Acquiring multi-seat locks in undefined order**
```python
# WRONG: order of seats is unpredictable → deadlock possible
seats = get_adjacent_seats(section='A', count=4)  # returns [A14, A12, A13, A15] (arbitrary)
for seat in seats:
    cursor.execute("SELECT ... FOR UPDATE WHERE seat_id=?", [seat])
# User A locks A12 first, User B locks A13 first → circular wait → deadlock
```
Fix: Always sort seat IDs before acquiring locks: `for seat in sorted(seats)`. Canonical ordering prevents circular wait by ensuring all transactions acquire locks in the same sequence.

---

## Production Incident Deep Dives

### Incident 4: UK Venue Bot Hold-and-Abandon Loop (2016)

**What happened:** A surprise show announced with 20,000 seats. Within 3 minutes, scalper bots using residential proxy IPs (20,000 unique IPs) placed holds on all 20,000 seats. Legitimate fans found "sold out." At minute 10, all 20,000 bot holds expired simultaneously. The hold expiry triggered a mass availability event — the seat map turned entirely green for 30 seconds. This triggered another wave of bot holds (same 20,000 IPs, new requests already queued). Cycle repeated 4 times over 40 minutes. Real fans could never complete checkout because by the time they were released from queue, bots had already re-filled all holds.

**Root cause:** No hold creation cost. Bots placed holds with zero economic risk. IP rate limiting at 1 hold/minute/IP was trivially bypassed with 20,000 residential IPs.

**Fixes applied:**
1. **Hold deposit:** $2 per hold, non-refundable on abandonment. Holding all 20,000 seats costs a bot $40,000 per cycle — economically nonviable.
2. **Account age requirement:** Accounts less than 30 days old cannot hold seats during first 30 minutes of sale (fan club pre-sale window).
3. **Graduated hold limits:** First purchase: hold up to 4 seats. No additional holds until first purchase confirmed.
4. **Bot behavioral scoring:** Holds placed within 2 seconds of sale open (before any human can navigate the seat map) are automatically flagged. Auto-challenged with CAPTCHA.

**Lesson:** Hold systems that are costless to abuse will be abused. Friction (financial, behavioral, or temporal) is more effective than technical countermeasures against sophisticated residential-proxy bot networks.

---

### Incident 5: FIFA World Cup 2022 — Payment Gateway Timeout Cascade

**Date:** November 2022, knockout stage ticket release.
**Duration:** 4 hours of severely degraded service.

**What happened:** Traffic was 8× tested capacity. The payment gateway's response time degraded from 2 seconds to 45 seconds under load. The Order Service used a thread-per-request model with a 10-minute payment timeout (set high to accommodate 3D-Secure bank challenges). With 45-second gateway calls: each thread blocked for 45 seconds. The 500-thread pool exhausted in seconds. New requests queued in an unbounded Java ExecutorService (LinkedBlockingQueue with no bound). As queue depth grew to millions of entries, heap exhaustion triggered OutOfMemoryError, crashing all Order Service pods. Load shifted to surviving pods, cascading crashes across the cluster.

**Seats remained HELD throughout** (no timeout triggered during the in-flight payment call) — users saw "payment processing" indefinitely, then the connection dropped on pod crash.

**Root cause:** Unbounded thread pool + high payment timeout + no circuit breaker + no back-pressure.

**Fix:**
```
1. Bounded thread pool:
   ThreadPoolExecutor(maxThreads=500, queueCapacity=1000, rejectPolicy=CallerRunsPolicy)
   → At 1001 queued requests, new requests run in caller thread or are rejected with 503
   
2. Short payment timeout:
   payment_gateway.charge(timeout=3000ms)  -- not 10 minutes
   On timeout: return hold to "payment pending" state, retry async
   
3. Circuit breaker on payment gateway:
   if (gateway.p95_latency > 5000ms) → open circuit for 30 seconds
   → return "payment queued" to user, process asynchronously when gateway recovers
   
4. Multiple payment gateways:
   Primary: Stripe. Secondary: Braintree.
   If primary error rate > 5% for 60 seconds → failover 50% traffic to secondary
```

**Lesson:** Any external call (payment gateway, fraud check) that can become slow under load must have: (a) a short timeout, (b) a bounded queue, and (c) a circuit breaker. One missing component is enough to cause a cascade.

---

### Incident 6: Coachella Ticket Transfer Double-Barcode (2019)

**What happened:** During high-volume ticket transfer processing (fans selling unused weekend passes), a race condition in the transfer API created two valid barcodes for the same seat on the same day. The original barcode was not invalidated before the new one was generated. Gate scanners (offline at the time due to connectivity issues) accepted both barcodes. Two people entered and attempted to sit in the same seat — security incident, police involvement, viral social media.

**Root cause:** The transfer operation was implemented as two separate steps:
```
Step 1: INSERT new barcode for recipient
Step 2: UPDATE original ticket status to TRANSFERRED  ← crash here during sync issue
```
When Step 2 failed silently, both the original and new barcode were valid. The offline gate scanner's 4-hour-old cache did not reflect the transfer at all.

**Fix:**
```sql
BEGIN;
-- Atomic invalidation + creation
UPDATE tickets SET status='TRANSFERRED', barcode_invalidated_at=NOW() 
WHERE ticket_id=? AND status='SOLD';  -- rows_affected must = 1

INSERT INTO tickets (barcode_id, event_id, seat_id, owner_user_id, status)
VALUES (NEW_BARCODE, event_id, seat_id, recipient_id, 'SOLD');
COMMIT;
```
One transaction — both barcode changes atomically or neither happens. Gate scanner cache refresh frequency increased from 4 hours to 30 minutes. High-risk tickets (transferred in last 2 hours) added to a real-time blacklist checked at gate even in offline mode.

---

## Additional Exercises

### Exercise 4: Idempotent Payment on Retry

**Problem:** A user clicks "Buy Now." Their browser shows a spinner for 35 seconds, then times out. They click again. The first request actually succeeded after 30 seconds. How do you prevent a double charge?

**Solution:**

```python
# Step 1: Client generates UUID at the moment user clicks "Buy Now"
idempotency_key = UUID.generate()
# Stored in sessionStorage — persists across browser retries but not refreshes

# Step 2: Client sends both requests with same key
POST /orders
Headers: { "Idempotency-Key": "9f8e7d6c-5b4a-..." }
Body: { "hold_id": "H123", "payment_method": "pm_abc" }

# Step 3: Server side
def create_order(hold_id, payment_method, idempotency_key):
    # Check for existing result
    existing = redis.get(f"idem:{idempotency_key}")
    if existing:
        return existing  # Return cached response immediately
    
    # Mark as in-progress
    redis.set(f"idem:{idempotency_key}", "IN_PROGRESS", ex=300)
    
    # Process the order
    result = process_payment_and_confirm(hold_id, payment_method)
    
    # Cache the result for 24 hours
    redis.set(f"idem:{idempotency_key}", result, ex=86400)
    return result

# Second request: redis.get returns the first result immediately.
# Payment provider also uses hold_id as its own idempotency key.
# Double protection: even if Redis fails, payment provider deduplicates.
```

---

### Exercise 5: GA Counter with Tier Inventory

**Problem:** Coachella 2024: 125,000 general admission tickets, split into 3 tiers: GA (100,000 at $429), GA+ (20,000 at $599), VIP (5,000 at $999). Design atomic hold and release operations. What happens if all GA sell out but GA+ remain?

**Solution:**

```sql
-- Schema
CREATE TABLE ga_inventory (
  event_id   BIGINT,
  tier_id    BIGINT,         -- 1=GA, 2=GA+, 3=VIP
  tier_name  VARCHAR(20),
  price_cents INT,
  total       INT,
  held        INT DEFAULT 0,
  sold        INT DEFAULT 0,
  PRIMARY KEY (event_id, tier_id)
);

-- Atomic hold (single tier)
UPDATE ga_inventory
SET held = held + 1
WHERE event_id = 5001
  AND tier_id = 1           -- GA tier
  AND (sold + held) < total;  -- not yet at capacity
-- rows_affected = 1: hold succeeded
-- rows_affected = 0: tier is full (sold out)

-- Atomic release on expiry
UPDATE ga_inventory
SET held = held - 1
WHERE event_id = 5001 AND tier_id = 1;

-- Atomic confirm on payment
BEGIN;
UPDATE ga_inventory SET held = held - 1, sold = sold + 1
WHERE event_id = 5001 AND tier_id = 1;
INSERT INTO tickets (event_id, tier_id, user_id, price_cents) VALUES (5001, 1, 789, 42900);
COMMIT;

-- Upsell flow: GA sold out → offer GA+ upgrade
availability = db.query("""
  SELECT tier_id, tier_name, price_cents, (total - held - sold) AS available
  FROM ga_inventory WHERE event_id=5001 ORDER BY tier_id
""")
-- If GA available=0, show "GA Sold Out" with "Upgrade to GA+ for $170 more" button
-- User confirms → hold against tier_id=2 (GA+)
```

---

## L5 vs L6 Calibration Table — Ticketing System

| Topic | L5 Answer | L6/Staff Answer |
|-------|-----------|-----------------|
| Overselling prevention | `UPDATE WHERE status='AVAILABLE'`, check rows_affected=1 | Same, plus SERIALIZABLE isolation for coordinated multi-seat holds; optimistic locking (version column) for read-heavy seat maps to reduce lock overhead |
| T=0 traffic | Virtual queue (Redis INCR), rate-limited release | Token bucket (Redis Lua script) for burst control; geographic queue sharding for global simultaneous sales; pre-warming autoscaling 30 min before sale open |
| Payment saga | hold → charge → confirm with compensating release on failure | Choreography (event-driven saga) vs orchestration (saga orchestrator with state machine); distributed transaction monitoring with automated rollback escalation after 5 min timeout |
| Hold expiry | Background job every 30s: `UPDATE WHERE hold_expires < NOW()` | Partitioned expiry index (`CREATE INDEX ON holds(hold_expires) WHERE status='HELD'`) for fast scan; Redis pub/sub for near-real-time expiry notification to WebSocket tier; per-event index partition to prevent lock contention on shared table |
| Bot prevention | CAPTCHA on queue join; IP rate limit; purchase limit per account | ML behavioral fingerprinting (cursor entropy, keystroke timing, navigation speed); device fingerprinting; hold deposit escrow; invisible CAPTCHA (reCAPTCHA v3 behavioral score); account reputation scoring |
| Seat map freshness | Redis HGETALL for all seat statuses; WebSocket push on status change | Delta compression (push only changed seat IDs, not full map); binary encoding (2 bits/seat = 17.5 KB for 70K seats vs 350 KB JSON); last-write-wins CRDT for concurrent updates from multiple service replicas |
| Barcode validation | DB lookup at gate; soft delete with 30-day recovery | Pre-loaded local SQLite cache at gate (refreshed every 30 min); cryptographically signed barcode (HMAC) for offline validation without network round-trip; real-time blacklist push for high-risk invalidations (last-hour refunds/transfers) |
| Audit trail | Kafka event log per state transition | Immutable append-only event store with signed event hashes (tamper detection); Event Sourcing pattern for complete saga replay; regulatory export format (SOC2, PCI-DSS 7-year retention) |
| Multi-region | Single DB primary + read replicas | Active-active with inventory partitioning (each region owns subset of seats); cross-region saga coordination via distributed saga orchestrator; conflict resolution via last-write-wins on hold creation (with hold_id ordering as tiebreak) |
| Dynamic pricing | current_price field updated by pricing engine; locked at hold creation | Real-time pricing model (ML-based demand forecasting per section per 5-min window); price floor/ceiling constraints per section per jurisdiction (consumer protection law compliance); price shown before hold locked in, confirmed before payment |

---

## Additional Exercises

### Exercise 6: Concurrent Multi-Seat Hold Deadlock Simulation

**Problem:** User A wants seats [A12, A13, A14, A15]. User B wants seats [A13, A14, A15, A16]. They both hit "hold" at exactly the same millisecond. Write the SQL execution trace for both the deadlock (wrong approach) and the deadlock-free solution (correct approach).

**Solution:**

```sql
-- WRONG APPROACH: arbitrary row lock order → deadlock

-- Thread A (User A's request):
BEGIN;
SELECT * FROM seats WHERE seat_id = 'A12' FOR UPDATE;  -- Acquires lock on A12
SELECT * FROM seats WHERE seat_id = 'A13' FOR UPDATE;  -- Acquires lock on A13
-- BLOCKED: Thread B holds A13 lock (see below)

-- Thread B (User B's request) - running concurrently:
BEGIN;
SELECT * FROM seats WHERE seat_id = 'A13' FOR UPDATE;  -- Acquires lock on A13
SELECT * FROM seats WHERE seat_id = 'A14' FOR UPDATE;  -- Acquires lock on A14
SELECT * FROM seats WHERE seat_id = 'A15' FOR UPDATE;  -- Acquires lock on A15
SELECT * FROM seats WHERE seat_id = 'A16' FOR UPDATE;  -- Acquires lock on A16
-- BLOCKED: Thread A holds A12, Thread A needs A13, Thread B holds A13, Thread B needs...
-- Wait: Thread A holds A12, wants A13 (held by B)
-- Thread B holds A13, wants to proceed to A14 (it already has it)
-- Actually Thread B got A13 before Thread A got there → Thread A blocks on A13
-- Thread B completes A14, A15, A16 and tries to commit → succeeds
-- Thread A then gets A13 → but A13 is now HELD by B → rows_affected < 4 → rollback

-- In this case no deadlock (B finishes before A gets A13)
-- BUT if Thread A gets A12, A13 and Thread B gets A14, A15, A16:
-- Thread A then wants A14 (held by B) → BLOCKS
-- Thread B then wants A12 or A13 → BOTH held by A → DEADLOCK!

-- Postgres detects the deadlock after ~1 second and aborts one transaction:
-- ERROR: deadlock detected. DETAIL: Process X waits for ShareLock on transaction Y

-- CORRECT APPROACH: sort seat IDs before acquiring locks → no circular wait

-- Both Thread A and Thread B sort their seat IDs first:
-- Thread A: sorted([A12, A13, A14, A15]) = [A12, A13, A14, A15]
-- Thread B: sorted([A13, A14, A15, A16]) = [A13, A14, A15, A16]

-- Both threads acquire locks in the SAME global order: A12 < A13 < A14 < A15 < A16
-- Thread A tries to lock A12 first → succeeds
-- Thread B tries to lock A13 first → A13 is not locked by A yet → succeeds
-- Thread A tries to lock A13 → BLOCKS (Thread B has it)
-- Thread B continues: A14, A15, A16 → all succeed
-- Thread B commits: holds (A13, A14, A15, A16) set to HELD
-- Thread B releases locks
-- Thread A unblocks at A13 → finds A13 is now HELD → rows_affected < 4 → rollback A12 → return "seats unavailable"
-- NO DEADLOCK: Thread B always gets its hold, Thread A cleanly fails and retries

-- SQL implementation:
def hold_seats(seat_ids, user_id, hold_duration_minutes=10):
    sorted_seats = sorted(seat_ids)  # canonical alphabetical order
    
    with db.transaction():
        rows = db.query("""
            SELECT seat_id, status FROM seats
            WHERE seat_id = ANY(?)
            ORDER BY seat_id ASC  -- same sort order in the database
            FOR UPDATE
        """, [sorted_seats])
        
        unavailable = [r for r in rows if r['status'] != 'AVAILABLE']
        if unavailable:
            db.rollback()
            return {"success": False, "unavailable_seats": [r['seat_id'] for r in unavailable]}
        
        db.execute("""
            UPDATE seats
            SET status = 'HELD',
                held_by_user_id = ?,
                hold_expires = NOW() + INTERVAL '? minutes'
            WHERE seat_id = ANY(?)
        """, [user_id, hold_duration_minutes, sorted_seats])
        
        return {"success": True, "held_seats": sorted_seats}
```

---

### Exercise 7: Virtual Queue Token Bucket Rate Limiter

**Problem:** The naive virtual queue releases exactly N users per second (fixed rate). Design a token bucket rate limiter that allows bursting: if no users were released in the last 10 seconds, up to 10×N users can be released in the next second, but sustained rate must not exceed N/sec.

**Solution:**

```python
# Token bucket in Redis using a Lua script (atomic check + update)

RATE_LIMIT_LUA = """
local key = KEYS[1]              -- "queue_bucket:{event_id}"
local capacity = tonumber(ARGV[1])  -- max_tokens (burst capacity)
local refill_rate = tonumber(ARGV[2])  -- tokens per second
local requested = tonumber(ARGV[3])   -- tokens requested (1 user = 1 token)
local now = tonumber(ARGV[4])         -- current timestamp (seconds, float)

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

-- Initialize if first request
if tokens == nil then
    tokens = capacity
    last_refill = now
end

-- Calculate how many tokens to add since last refill
local elapsed = now - last_refill
local new_tokens = elapsed * refill_rate
tokens = math.min(capacity, tokens + new_tokens)

-- Check if request can be granted
if tokens >= requested then
    tokens = tokens - requested
    redis.call("HSET", key, "tokens", tokens, "last_refill", now)
    redis.call("EXPIRE", key, 3600)
    return 1  -- granted
else
    redis.call("HSET", key, "tokens", tokens, "last_refill", now)
    redis.call("EXPIRE", key, 3600)
    return 0  -- denied
end
"""

def release_from_queue(event_id, user_id, base_rate=1000):
    """
    Attempt to release one user from the queue.
    base_rate: tokens per second (normal release rate)
    capacity: 10× base_rate (burst capacity for 10 seconds of buildup)
    """
    now = time.time()
    capacity = base_rate * 10  # 10-second burst window
    
    result = redis.eval(
        RATE_LIMIT_LUA,
        1,                  # number of KEYS
        f"queue_bucket:{event_id}",  # KEYS[1]
        capacity,           # ARGV[1]
        base_rate,          # ARGV[2]
        1,                  # ARGV[3] - one token per user
        now                 # ARGV[4]
    )
    
    if result == 1:
        # Grant access to seat selection
        queue_position = redis.lpop(f"queue:{event_id}")
        if queue_position:
            grant_seat_selection_access(user_id, event_id)
            return {"status": "granted", "proceed_to": "/seat_selection"}
    
    return {"status": "queued", "position": get_queue_position(user_id, event_id)}

# Behavior with bursting:
# T=0: Event opens. 10,000 tokens available (10s × 1,000/s)
# T=0 to T=10: Drain bucket at 10,000 users/sec? No — the bucket starts full but
#   the REFILL rate is 1,000/sec, so max burst across the first second is 10,000.
# T=0 to T=1: 10,000 users released (token bucket starts full at capacity=10,000)
# T=1 to T=2: 1,000 more released (refill rate = 1,000/sec)
# Steady state: 1,000/sec
# This gives a controlled burst at T=0 (letting first 10K users through quickly)
# then sustained 1,000/sec release thereafter.
```

---

### Exercise 8: Barcode Signing for Offline Gate Validation

**Problem:** Design a cryptographically signed barcode that the gate scanner can validate without a network call. The scanner must detect: (1) invalid barcode, (2) barcode for wrong event, (3) expired barcode (event date has passed).

**Solution:**

```python
import hmac, hashlib, struct, time

SERVER_SECRET = b"your-256-bit-secret-key"  # stored in HSM, never in code

def generate_barcode(ticket_id, event_id, seat_id, event_date_unix):
    """
    Barcode = base62_encode(ticket_id || event_id || event_date || HMAC)
    """
    # Pack data fields (fixed-length binary)
    data = struct.pack(">QQQi",  # 8+8+8+4 = 28 bytes
        ticket_id,          # 8 bytes: unique ticket identifier
        event_id,           # 8 bytes: which event
        seat_id,            # 8 bytes: which seat (or 0 for GA)
        event_date_unix     # 4 bytes: event date as Unix timestamp (day granularity)
    )
    
    # HMAC-SHA256 of the data (first 8 bytes = 64-bit truncated MAC)
    mac = hmac.new(SERVER_SECRET, data, hashlib.sha256).digest()[:8]
    
    # Barcode = data (28 bytes) + mac (8 bytes) = 36 bytes
    barcode_bytes = data + mac
    
    # Encode as base62 (URL-safe, printable) → ~48 characters
    return base62_encode(barcode_bytes)

def validate_barcode_offline(barcode_string, current_date_unix):
    """
    Gate scanner validates without network. Only needs:
    - SERVER_SECRET (loaded at start of shift, never transmitted after)
    - current_date_unix (from scanner's local clock)
    """
    try:
        barcode_bytes = base62_decode(barcode_string)
    except:
        return {"valid": False, "reason": "Invalid barcode format"}
    
    if len(barcode_bytes) != 36:
        return {"valid": False, "reason": "Invalid barcode length"}
    
    data, received_mac = barcode_bytes[:28], barcode_bytes[28:]
    
    # Verify HMAC
    expected_mac = hmac.new(SERVER_SECRET, data, hashlib.sha256).digest()[:8]
    if not hmac.compare_digest(received_mac, expected_mac):
        return {"valid": False, "reason": "Invalid barcode — not issued by system"}
    
    # Unpack fields
    ticket_id, event_id, seat_id, event_date_unix = struct.unpack(">QQQi", data)
    
    # Check event date (allow ±1 day window for timezone differences)
    if abs(event_date_unix - current_date_unix) > 86400:
        return {"valid": False, "reason": f"Barcode is for a different date"}
    
    # Check against local blacklist (refunded/transferred tickets loaded at shift start)
    if ticket_id in LOCAL_BLACKLIST:
        return {"valid": False, "reason": "Ticket has been invalidated"}
    
    return {
        "valid": True,
        "ticket_id": ticket_id,
        "event_id": event_id,
        "seat_id": seat_id
    }

# Security properties:
# - No network required for validation
# - Forgery requires HMAC collision (negligible probability) or key theft
# - Event-bound: barcode for yesterday's show rejected today (event_date check)
# - Blacklist: downloaded at shift start, refreshed every 30 min
#   For revocations in last 30 min: online validation triggered by "check online" flag
```

---

## Key Interview Signals — What L5 Looks Like In the Room

**Signal 1: You identify the race condition in the two-step hold pattern immediately.**
The most common mistake in ticketing interviews is describing "check availability, then reserve." L5 candidates recognize this pattern as a time-of-check-time-of-use (TOCTOU) race condition and immediately propose the single-statement atomic solution: `UPDATE WHERE status='AVAILABLE'` with rows_affected check. Candidates who need the interviewer to probe for the race condition are missing a key L5 signal.

**Signal 2: You explain the hold expiry background job correctly.**
Weak candidates say "use a scheduled job to clean up holds." L5 candidates give: (1) the job runs every 30 seconds, (2) the query uses a partial index on `hold_expires WHERE status='HELD'` (not a full table scan), (3) the job batches updates (not one UPDATE per expired hold), and (4) the job has idempotency — running twice within 30 seconds is safe (UPDATE WHERE is idempotent).

**Signal 3: You address the virtual queue as a traffic shaping mechanism, not a UX feature.**
Many candidates present the queue as "making users feel better about waiting." L5 candidates present it as a traffic control mechanism: without the queue, the database sees a spike of millions of concurrent write transactions — which saturates connection pools and causes cascading failures. The queue transforms a spike into a steady stream. This framing demonstrates you understand the system's failure modes, not just its features.

**Signal 4: You use the saga pattern correctly with compensating transactions.**
When asked about payment failures after a successful hold, weak candidates say "roll back the hold." L5 candidates describe the saga: the hold and payment are separate local transactions, not a distributed transaction. When payment fails, a compensating transaction (release the hold) restores consistency. The key insight: you cannot have a distributed atomic transaction across the seat service and the payment service — the saga pattern is how distributed systems achieve eventual consistency without 2-phase commit.

**Signal 5: You answer the idempotency question with both layers.**
When asked "how do you prevent double-charging on payment retry?", the complete answer has two layers: (1) the application layer uses `Idempotency-Key: hold_id` in the payment API call, so the payment provider deduplicates at its end, and (2) the hold_id is stored in the orders table, so even if the application retries after the order was created, the `ON CONFLICT (hold_id) DO NOTHING` ensures the order is not duplicated. One layer is a good answer. Both layers is an L5 answer.

---

## Related Topics to Review After This Chapter

- **Ch58 (Payment Flow):** The saga pattern (hold → charge → confirm) is the ticketing-specific version of the general payment saga covered in Ch58. Ch58 covers the 3DS authentication flow, payment gateway retry semantics, and settlement timing. The idempotency key pattern used here maps directly to the idempotency pattern in Ch58's payment processing.
- **Ch61d (Hotel Reservation):** Hotel reservation is the closest architectural sibling to ticketing — both involve temporal holds on finite inventory. The key differences: hotel rooms are held for days (not minutes), so TTL-based expiry is less viable; hotels use date-range inventory with per-night availability. The atomic UPDATE WHERE pattern is identical. If you're comfortable with ticketing, hotel reservation is straightforward.
- **Ch33 (Caching at Scale):** The seat map (Redis HGETALL for all seat statuses) is a bulk-read caching problem. The CDN-cached seat map snapshot (updated every 10 seconds) is the CDN caching layer. Ch33 covers the trade-offs between different cache granularities — per-seat TTL vs. full-map TTL vs. WebSocket invalidation push — in a general framework.
- **Redis Lua scripting (external reading):** The token bucket rate limiter for the virtual queue uses a Redis Lua script. Understanding how to write atomic Lua scripts in Redis (KEYS, ARGV, redis.call, atomic execution guarantee) is a practical skill worth learning before any interview at a company with high write throughput. Search "Redis Lua scripting tutorial" for a practical introduction.
- **Stripe idempotency documentation (external reading):** Stripe's idempotency key implementation is the production reference for the payment idempotency pattern described in this chapter. Their public documentation explains exactly how they deduplicate, how long they retain results, and what happens when two concurrent requests use the same key. Understanding this makes your explanation of idempotency keys more precise in an interview.

---

## Quick Reference: Database Operations in the Ticketing Hot Path

| Operation | SQL Pattern | Rows Affected Check | Failure Response |
|-----------|-------------|---------------------|------------------|
| Hold single seat | `UPDATE seats SET status='HELD' WHERE seat_id=? AND status='AVAILABLE'` | == 1 → success | 0 → seat taken, show error |
| Hold N seats | `UPDATE seats SET status='HELD' WHERE seat_id IN (?) AND status='AVAILABLE'` | == N → success | < N → partial hold, release all |
| Release expired holds | `UPDATE seats SET status='AVAILABLE' WHERE status='HELD' AND hold_expires < NOW()` | any → ok | — |
| Confirm purchase | `UPDATE seats SET status='SOLD' WHERE seat_id=? AND status='HELD' AND held_by=?` | == 1 → success | 0 → hold expired during payment |
| GA decrement | `UPDATE ga_inventory SET held=held+1 WHERE (sold+held)<total` | == 1 → success | 0 → sold out |

---

## Ticketing System Components Summary

### Data Flow at T=0 (Flash Sale Open)

```
T=0: Sale opens
  ├─ 14M users send queue join requests
  │   └─ Redis INCR → assign position number (atomic, O(1))
  │       └─ Return: {"position": 1,234,567, "estimated_wait": "12 min"}
  │
  ├─ Users browse seat map while waiting
  │   └─ Redis HGETALL seat_map:{event_id} → 70KB payload (CDN cached, 10s TTL)
  │
  └─ Queue releases 1,000 users/sec to seat selection
      ├─ User selects seat A12
      ├─ POST /holds:
      │   UPDATE seats SET status='HELD' WHERE seat_id='A12' AND status='AVAILABLE'
      │   INSERT INTO holds (hold_id, seat_id, user_id, hold_expires)
      │   WebSocket push to seat map browsers: {"seat": "A12", "status": "HELD"}
      │
      ├─ User pays within 10 min:
      │   POST /orders (Idempotency-Key: {hold_id})
      │   → Payment Service: charge_card(idempotency_key=hold_id)
      │   → UPDATE seats SET status='SOLD', UPDATE holds SET status='COMPLETED'
      │   → INSERT INTO orders, INSERT INTO tickets (with barcode)
      │   → WebSocket push: {"seat": "A12", "status": "SOLD"}
      │
      └─ Or hold expires (no payment in 10 min):
          Background job: UPDATE seats SET status='AVAILABLE' WHERE hold_expires < NOW()
          → WebSocket push: {"seat": "A12", "status": "AVAILABLE"}  ← seat turns green again

Every transition is published to Kafka "seat_state_transitions" for:
  - Audit trail (immutable log)
  - Notification service (send confirmation email)
  - Analytics (sale velocity, abandonment rate, bot detection)
```

### Three Invariants That Must Never Be Violated

1. **At most one HELD or SOLD record per seat per event.** Enforced by the atomic UPDATE WHERE + rows_affected check. A UNIQUE constraint on `(seat_id, event_id)` in the `seat_inventory` table enforces this at the database level as a belt-and-suspenders backup.

2. **Payment is never charged for an expired hold.** Before calling the payment service, always check `hold_expires > NOW()`. The hold_id is the authority — if the hold record's expires field is in the past, reject the payment request with `409 Hold Expired`, not `500`.

3. **No ticket exists without a confirmed payment.** The INSERT INTO tickets happens inside the same transaction as the seat status update to SOLD. If the ticket insert fails, the seat remains HELD (not SOLD), and the payment must be refunded via the compensating transaction. Tickets are created atomically with the seat status change, never in a separate step.

---

## Quick Reference: Hold System State Diagram

```
                    ┌─────────────────────────────────────┐
                    │                                     │
              AVAILABLE ─────────────────────────────────►│
                  │  ▲                                    │
  atomic UPDATE   │  │ hold expires (background job)      │
  WHERE status=   │  │ OR payment fails (compensate)      │
  'AVAILABLE'     ▼  │                                    │
              HELD ──┘                                    │
                  │                                       │
                  │ payment succeeds (confirm)            │
                  ▼                                       │
              SOLD ──────────────────────────────────────►│
                  │                                       │
                  │ refund requested                      │
                  ▼                                       │
           REFUNDED ─────────────────────────────────────►│
                  │                                       │
                  │ barcode scanned at gate               │
                  ▼                                       │
           SCANNED (terminal state)                       │
                    │                                     │
                    └─────────────────────────────────────┘
                                 DB states

Barcode validity (at gate):
  SOLD + not scanned → VALID (admit)
  SCANNED → DUPLICATE (reject — show first scan timestamp)
  REFUNDED → INVALID (reject — refunded after purchase)
  TRANSFERRED → INVALID for original ticket (new barcode is VALID)
```

**The five-minute window test:** mentally trace any sequence of events (user holds seat, pays, ticket is generated, user transfers ticket, original user shows up at gate) through this state diagram. If the diagram handles it without ambiguity, the schema is correct. If you find a sequence that puts the ticket in two valid states simultaneously, you've found a schema bug.
