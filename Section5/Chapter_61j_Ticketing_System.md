# Chapter 61j: Ticketing System — Ticketmaster / Concert Seats

> When Taylor Swift tickets go on sale, 14 million people hit "buy" in the
> first minute. Your database has 60,000 seats. You need to sell exactly
> 60,000 tickets — not 59,999, not 60,001 — while every user thinks
> they're first in line.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Ticketing systems are the canonical flash-sale and inventory concurrency problem.
They appear in interviews at companies running marketplaces, e-commerce platforms,
and event systems. The core challenge — preventing overselling while staying
responsive under extreme load — teaches optimistic locking, seat reservation
hold patterns, and queue-based traffic shaping. Pairs naturally with Ch113
(Hotel Reservation) but at a much more extreme concurrency level.

---

## Planned Content

### Part 1: Requirements and Scale
- Users browse events, select seats, purchase tickets before others take them
- Functional: browse events, view seat map, hold a seat, purchase, view booking, transfer ticket
- Non-functional: no overselling (exactly 60K seats sold), < 500ms seat hold response, handle 10M concurrent users at sale start
- Scale: 10M users hit the system simultaneously at T=0; normal traffic is 10K req/sec
- Not in scope: payments (Ch58), fraud detection, ticket transfer

### Part 2: The Core Problem — Race Conditions at Flash Sale Start
- At T=0 (sale opens), 10M users simultaneously send "reserve seat A12"
- Naive: SELECT available seats → user picks seat → INSERT reservation — WRONG: 1000 users see the same seat as available simultaneously
- The fix requires that checking availability and claiming the seat are atomic

### Part 3: Seat Hold Pattern — The Two-Phase Approach
- Phase 1 — Hold (temporary reservation, 10 minutes):
  - User selects seat → system atomically marks it as HELD with an expiry timestamp
  - Implementation: UPDATE seats SET status='HELD', held_by=user_id, hold_expires=NOW()+10min
    WHERE seat_id=? AND status='AVAILABLE'
  - If 0 rows updated → seat taken → return "seat unavailable"
  - User proceeds to payment page with a 10-minute countdown
- Phase 2 — Confirm (on payment success):
  - UPDATE seats SET status='SOLD', order_id=?
    WHERE seat_id=? AND held_by=user_id AND hold_expires > NOW()
  - If 0 rows updated → hold expired → payment rejected → user must restart
- Hold expiry: background job or cron runs every 30s, releases expired holds:
  UPDATE seats SET status='AVAILABLE' WHERE status='HELD' AND hold_expires < NOW()

### Part 4: Traffic Shaping — Protecting the System at T=0
- 10M concurrent users at T=0 will kill any database
- Virtual queue: at T=0, immediately send all incoming users to a waiting room
  - Issue each user a queue position token (Redis INCR counter → position number)
  - Show a countdown: "You are #4,231,089 in line. Estimated wait: 8 minutes"
  - Process N users per second (e.g., 10,000/sec) from the front of the queue
- Queue implementation: Redis list or SortedSet (score = arrival timestamp)
- Token: JWT with queue position + expiry; user presents token to enter the sale
- Result: database sees steady 10K req/sec instead of 10M/sec spike

### Part 5: Seat Map and Availability
- Seat map: ~60,000 seats per venue, each with section/row/seat number, price tier, accessibility flag
- Availability display: read from Redis cache (not DB) — can tolerate slight staleness
  - Cache: hash map of seat_id → status (AVAILABLE/HELD/SOLD)
  - Updated on every status change; TTL 30s for safety
- Real-time updates: WebSocket push to all browsing users when seat status changes
  - Seat turns red when someone else holds it; turns green when hold expires
- Pagination: for large venues, return one section at a time (not all 60K seats at once)

### Part 6: Idempotency and Payment Integration
- User submits payment → payment service charges card → calls back to confirm ticket
- Idempotency key (UUID) per purchase attempt — prevents double-charging on retry
- Saga pattern: hold seat → charge payment → confirm ticket (all three must succeed)
  - Payment fails → release hold → inventory restored
  - Confirm fails → refund payment → release hold (compensating transaction)
- Distributed transaction: use choreography-based saga (events via Kafka) not 2PC

### Part 7: System Architecture
- Queue service: Redis-based virtual waiting room at T=0; issues ordered tokens
- Seat service: manages seat status (AVAILABLE/HELD/SOLD) in DB + Redis cache
- Order service: orchestrates hold → payment → confirm saga; stores order records
- Notification service: sends confirmation email + digital ticket (PDF/barcode) after purchase
- Event service: event metadata, venue seat map, pricing tiers

### Part 8: Interview Framework
- Immediately raise the overselling problem — this is what makes the question interesting
- Walk the two-phase hold pattern before anything else
- Then add the virtual queue — interviewers often ask "how do you handle the traffic spike?"
- Cover the saga for payment failure — what happens if payment succeeds but confirm fails?
- L5 bar: atomic seat hold (UPDATE with row-count check), hold expiry, virtual queue, idempotency
- L6 bar: multi-region for global events, dynamic pricing (price updates during high demand),
  ticket transfer/resale system, mobile app offline ticket storage

---

## The One-Sentence Summary

> "Ticketing = two-phase hold pattern (atomic UPDATE seats WHERE status='AVAILABLE' → 0 rows = sold out) + 10-minute hold expiry (background release job) + virtual waiting room (Redis queue + rate-limited entry at T=0) + saga for payment failure (compensating hold release) — the insight is that checking availability and claiming must be one atomic DB operation, not two separate steps."

---

*Full chapter: ~2,500 lines. Section 5 — L5 / Senior SWE. Pairs with Ch113 (Hotel Reservation).*
