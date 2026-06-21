# Chapter 61h: Ride Sharing — Uber / Lyft

> Uber's core problem sounds simple: match a rider to a nearby driver.
> At peak in NYC, there are 80,000 drivers broadcasting their location
> 4 times per second. Finding the nearest available driver to any rider
> in under 500ms requires a very different architecture than a typical
> web application.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Ride sharing is one of the most commonly asked system design questions at L5/L6.
It combines location tracking, geospatial matching, real-time messaging, and
pricing into one system. It is distinct from Ch87 (Location & Maps), which covers
map rendering and routing algorithms. This chapter covers the dispatch system:
how do you efficiently match riders and drivers, handle surge pricing, and track
live location at scale?

---

## Planned Content

### Part 1: Requirements and Scale
- Rider requests a ride → system finds nearest available driver → driver accepts → trip happens
- Functional: request ride, match driver, track trip in real-time, calculate fare, payment
- Non-functional: driver match < 1s, location updates every 4s, handle 1M concurrent drivers
- Scale: 1M drivers online simultaneously, 10M ride requests/day, 40M location updates/min
- Not in scope: mapping/routing (use Google Maps API), payments (Ch58), driver app

### Part 2: Location Tracking — The Hottest Write Path
- Every driver sends GPS coordinates every 4 seconds
- 1M drivers × 1 update/4s = 250K writes/sec — this is the hardest part of the system
- Storage: do NOT write every update to a relational DB — use Redis (in-memory, fast)
- Redis GEOADD: `GEOADD drivers <lng> <lat> <driver_id>` — stores location in a geospatial index
- Redis GEORADIUS: find all drivers within R km of a point — returns sorted by distance
- Why Redis Geo works: internally uses GeoHash encoded as a sorted set score — O(log N + M) search
- Persistence: async flush driver locations to Cassandra for trip history; Redis is the live index

### Part 3: Driver Matching
- Rider submits request with their location and ride type (UberX, Pool, Black)
- Matching service queries Redis: `GEORADIUS drivers <rider_lat> <rider_lng> 5km ASC COUNT 10`
- Returns 10 nearest available drivers within 5km
- Rank by: distance + driver rating + estimated pickup time
- Offer to best driver first; wait 10s; if no accept → offer to next driver
- Driver state machine: AVAILABLE → OFFERED → EN_ROUTE → ON_TRIP → AVAILABLE
  - Store state in Redis (fast lookup) + DB (persistence)

### Part 4: The Trip State Machine
- States: REQUESTED → MATCHED → DRIVER_EN_ROUTE → RIDER_PICKED_UP → COMPLETED / CANCELLED
- Event stream: each state transition published to Kafka
  - MATCHED event → notify driver app (push notification)
  - DRIVER_EN_ROUTE → rider app starts showing driver's live location
  - RIDER_PICKED_UP → start the meter
  - COMPLETED → trigger fare calculation + payment
- Consumers: notification service, fare service, analytics, driver earnings service

### Part 5: Live Trip Tracking (Rider Watching Driver Approach)
- During EN_ROUTE: rider app shows driver's dot moving on a map
- Driver app sends location every 4s → location service → WebSocket push to rider app
- Alternative: rider app polls location service every 4s (simpler, slightly higher latency)
- Location service: Redis lookup of driver's current location → return to rider
- Map rendering: rider app overlays driver location on map tiles from Google Maps API

### Part 6: Surge Pricing
- When demand > supply in an area, Uber raises prices to attract more drivers
- Demand signal: count ride requests per hexagonal geo-cell (H3 library) per minute
- Supply signal: count available drivers per cell
- Surge multiplier: if requests/drivers > threshold → apply 1.5×, 2×, etc.
- Calculation: every 5 minutes, batch job computes surge multiplier per H3 cell
- Display: before rider confirms, show surge price prominently with countdown timer

### Part 7: System Architecture
- Driver location service: receives location pings → writes to Redis GEOADD → async flush to Cassandra
- Matching service: GEORADIUS query → rank drivers → send offer → handle accept/reject
- Trip service: manages trip state machine; stores in DB; publishes events to Kafka
- Notification service: pushes state changes to driver/rider apps (APNs/FCM for mobile, WebSocket for web)
- Pricing service: calculates fare from distance + time + surge multiplier
- Map service: wraps Google Maps API for routing (ETA, directions)

### Part 8: Interview Framework
- Open by separating the sub-problems: location tracking, matching, trip management, pricing
- Lead with the location tracking write problem — 250K writes/sec is the bottleneck to solve first
- Explain Redis GEOADD/GEORADIUS — this is the key data structure, similar to Leaderboard ZSET
- Walk the matching flow step by step including the offer/accept retry logic
- L5 bar: location tracking with Redis Geo, matching within radius, trip state machine
- L6 bar: global rollout (region-partitioned Redis clusters), handling network partition
  during active trips, ETA prediction model, driver supply forecasting

---

## The One-Sentence Summary

> "Ride sharing = Redis GEOADD for real-time driver location (250K writes/sec) + GEORADIUS for nearest available driver matching + trip state machine (REQUESTED→MATCHED→EN_ROUTE→COMPLETED) published to Kafka + WebSocket for live location push to rider — the hardest part is the location write throughput, solved by keeping the live index in Redis and async-flushing history to Cassandra."

---

*Full chapter: ~2,500 lines. Section 5 — L5 / Senior SWE. Distinct from Ch87 (geo/routing); Ch112 (static POI search).*
