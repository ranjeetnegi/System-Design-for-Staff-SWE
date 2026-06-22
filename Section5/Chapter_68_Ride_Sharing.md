# Chapter 61h: Ride Sharing — Uber / Lyft

> Uber's core problem sounds simple: match a rider to a nearby driver.
> At peak in NYC, there are 80,000 drivers broadcasting their location
> 4 times per second. Finding the nearest available driver to any rider
> in under 500ms requires a very different architecture than a typical
> web application.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Ride Sharing (Uber/Lyft)                  |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (dispatch only? payments? pooling?)   |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                           |
|                                                                  |
|  The clarifying question that changes everything:                |
|  "Are we building the dispatch system (match rider to driver)   |
|   or the full product including mapping, payments, and driver   |
|   earnings?" Most interviewers want dispatch + location tracking.|
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Redis GEOADD for driver location, GEORADIUS for matching     |
|  - Why Redis Geo works (GeoHash encoded as ZSET score)          |
|  - Trip state machine: REQUESTED->MATCHED->EN_ROUTE->COMPLETED  |
|  - Kafka event stream for state transitions                     |
|  - Surge pricing: supply/demand ratio per geo-cell              |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Region-partitioned Redis clusters (avoid cross-region look-  |
|    up for NYC drivers when serving SF rider request)            |
|  - ETA prediction beyond Google Maps API (ML model)            |
|  - Supply forecasting (predict where drivers will be needed)    |
|  - Handling active trip during Redis failover                   |
|  - Consistent hashing for driver location shard assignment      |
+------------------------------------------------------------------+
```

---

## Why This Chapter Matters

Ride sharing is asked at nearly every L5/L6 interview at Uber, Lyft, DoorDash, Instacart, and any company with a marketplace or real-time logistics problem. The question tests your ability to separate a complex product into tractable sub-problems: location tracking, geospatial search, state machine management, and real-time push notifications. Interviewers reward candidates who immediately identify "the write bottleneck is 250K location updates per second" and explain why Redis is the right tool before any other.

This chapter covers the dispatch system only — not map rendering (Ch87), not payment processing (Ch58). The dispatch problem is: given a rider's location, find the best available driver within a reasonable distance, offer them the trip, handle accept/reject, and track the trip through completion.

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify first

"What is the scope? The full Uber product (mapping, payments, ratings, driver earnings, surge) or the core dispatch system (location tracking + matching + trip management)?" Most interviews want the dispatch system.

Secondary clarifications:
1. "Do we need ride pooling (multiple riders in one car)?" Pool changes the matching algorithm significantly.
2. "Multiple ride types (UberX, UberBlack, motorcycle)?" Requires per-type driver pools.
3. "Real-time ETA display or just distance-based matching?" ETA requires integration with a routing API.
4. "Global (multi-region) or single city?" Multi-region changes sharding strategy.

For this chapter: dispatch system only, no pooling, UberX-only (single type), real-time ETA with Google Maps API, global multi-region.

### Who uses the ride sharing system?

**Riders:**
- Request a ride by opening the app and entering a destination
- See estimated price and ETA before confirming
- Track driver's live location while en route
- Pay on trip completion (no cash handling in scope)

**Drivers:**
- Broadcast GPS location every 4 seconds while online
- Receive trip offers (accept or reject within 10 seconds)
- Navigate to pickup point, then to destination
- See earnings for the trip after completion

**Internal systems:**
- Analytics: every location ping, trip event, and price calculation recorded for insight
- Fraud detection: abnormal routes, fake GPS coordinates, price manipulation
- Supply forecasting: predict where drivers will be needed 30 minutes from now

### Core use cases

**P0 — Must have:**
- UC1: Driver goes online → location tracked in real time
- UC2: Rider requests a ride → nearest available driver matched within 1 second
- UC3: Driver accepts → rider sees driver location live, ETA updated continuously
- UC4: Trip completes → fare calculated → payment triggered

**P1 — Important:**
- UC5: Surge pricing displayed before rider confirms (demand > supply in area)
- UC6: Driver rejects → offer sent to next driver in ranked list
- UC7: Trip cancelled by rider or driver → appropriate state transitions and fees

**Out of scope:**
- Turn-by-turn navigation (use Google Maps/Apple Maps in driver app)
- Payment processing (Ch58)
- Driver background checks and onboarding
- Ride pooling (different matching algorithm)

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Driver-side operations

- **F1:** `driver_location_update(driver_id, lat, lng, heading, speed)` — driver app sends every 4 seconds
- **F2:** `driver_go_online(driver_id)` — driver marks themselves available for trips
- **F3:** `driver_go_offline(driver_id)` — driver marks themselves unavailable
- **F4:** `driver_accept_trip(trip_id)` — driver accepts an offered trip
- **F5:** `driver_reject_trip(trip_id)` — driver declines; system offers to next driver

### Rider-side operations

- **F6:** `rider_request_ride(rider_lat, rider_lng, dest_lat, dest_lng) -> trip_id, estimated_price, eta`
- **F7:** `rider_get_trip_status(trip_id) -> state, driver_location, driver_eta`
- **F8:** `rider_cancel_trip(trip_id)` — cancel before driver arrives

### System operations

- **F9:** `find_nearest_drivers(lat, lng, radius, ride_type) -> [(driver_id, distance, eta), ...]`
- **F10:** `calculate_fare(trip_id) -> base_fare + distance_fare + time_fare + surge_multiplier`
- **F11:** `get_surge_multiplier(lat, lng) -> multiplier` — price multiplier for the area

### The core matchmaking constraint

```
Time budget: rider requests ride -> driver offered -> driver accepts = total < 5 seconds
  Breakdown:
  - Find nearest drivers: < 500ms (Redis GEORADIUS)
  - Rank drivers (distance + rating + ETA): < 100ms
  - Send offer to driver: < 100ms (push notification)
  - Driver sees offer on screen: depends on driver's phone (not our SLA)
  - Driver accepts: up to 10 seconds (human response time)
  - Trip matched notification to rider: < 100ms

  Total from "request" to "matched" confirmation: ~12 seconds at most
  (10s for driver to accept + 2s system latency)
```

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### Traffic numbers

```
Drivers online simultaneously:   1,000,000 (global)
Location updates per driver:      1 per 4 seconds
Location updates total:           1M / 4 = 250,000 writes/sec  ← THE HOT PATH

Ride requests per day:            10,000,000
Peak ride requests:               10M / 86400s * 3 (peak factor) = 347 requests/sec
  (Most rides happen during rush hours — 2-hour windows morning and evening)

Trip events (Kafka):
  Each trip: ~10 state transitions (REQUESTED, MATCHED, EN_ROUTE, PICKUP, COMPLETED, ...)
  10M trips/day * 10 events = 100M events/day = 1,157 events/sec

Live tracking reads:
  During EN_ROUTE and ON_TRIP phases: rider polls driver location every 4 seconds
  Average trip duration: 15 minutes = 900 seconds / 4 = 225 location polls per trip
  Active trips at peak: 347 requests/sec * 60% acceptance rate * 15min duration = ~313K active trips
  Location reads: 313K trips * 1 read/4s = 78K reads/sec

The hardest number to handle: 250K location writes/sec
```

### Redis Geo memory math

```
Redis GEOADD stores each driver as a ZSET member with a geohash score:
  Per driver: ~50-70 bytes (ZSET member with geo-encoded score)

1M drivers * 70 bytes = 70 MB
Even with 10M registered drivers (including offline): 700 MB

Conclusion: all drivers fit in a single Redis instance (16 GB).
But for write throughput: 250K GEOADD/sec exceeds single-instance capacity.
Redis: ~100K-500K ops/sec single-threaded.

Fix: geo-partition drivers across Redis instances by city/region:
  NYC Redis instance: 80K drivers -> handles 80K/4 = 20K GEOADD/sec. Fine.
  SF Redis instance:  20K drivers -> handles 20K/4 = 5K GEOADD/sec. Fine.
  LA Redis instance:  30K drivers -> handles 30K/4 = 7.5K GEOADD/sec. Fine.
  ...
  Each city's Redis instance handles only that city's drivers.
  A ride request in NYC only queries NYC's Redis. No cross-region fan-out.
  
  Shard assignment: by city (coarse-grained) or by geohash prefix (fine-grained).
  For global scale: consistent hashing of geohash prefix -> Redis shard assignment.
```

### Cassandra for location history

```
Driver location history (for trip replay, auditing, fraud detection):
  1M drivers * 250K updates/sec * 16 bytes (lat/lng/ts compressed) = 4 GB/sec write
  In practice: 250K * 20 bytes = 5 MB/sec to Cassandra (async, batched)
  Cassandra write throughput: 100K-500K writes/sec per node. 5 nodes for 250K writes/sec.
  
  Schema:
    Partition key: driver_id
    Clustering key: ts (timestamp) DESC
    Columns: lat, lng, heading, speed
    TTL: 30 days (older than 30 days: automatically deleted)
  
  Reads: trip replay queries a specific driver_id + time range.
    SELECT * FROM driver_locations WHERE driver_id = ? AND ts BETWEEN ? AND ?
    This is a single-partition range scan. Efficient.
```

---

## Phase 4: Non-Functional Requirements (Minutes 14-19)

### Latency

- Driver location update: < 100ms round-trip acknowledged (fire-and-forget is acceptable — drivers do not wait for acknowledgment)
- Rider-to-match latency: < 12 seconds (human driver response time dominates)
- Location update visible to rider: < 2 seconds after driver sends update (driver sends every 4s)
- Surge pricing update: 5-minute granularity is acceptable

### Consistency

- **Driver availability state:** Must be strongly consistent. A driver cannot be offered two trips simultaneously. Availability transitions must be atomic.
- **Location data:** Eventual consistency is fine. If a driver's location shows 10-second-old coordinates, matching still works within acceptable accuracy.
- **Trip state:** Eventually consistent across rider and driver apps (within 1 second). Ordering is guaranteed by Kafka (total order within a trip's partition).

### Availability

- 99.99% for location tracking and matching (high-value core path). 52 minutes downtime/year.
- Matching service partial degradation: if a city's Redis fails, expand search radius or fall back to nearest-city Redis. Degrade gracefully rather than full outage.

---

## Phase 5: Assumptions and Constraints

- A1: GPS coordinates are trusted (no client-side spoofing detection in this design).
- A2: Matching radius: 5 km initial search, expand to 10 km if no driver found within 5 km.
- A3: Driver offer timeout: 10 seconds. If driver doesn't respond, offer to next driver in ranked list.
- A4: Maximum offer attempts: 5 drivers in a row. If all reject: trip request fails, rider told to retry.
- A5: ETA is calculated by calling Google Maps Directions API (or similar). Not computed in-house.
- A6: Trip fare is calculated on server side after trip completes (not client side — prevents manipulation).

---

## Architecture Design — HLD

### Opening analogy

Imagine a city's 911 dispatch center. When a call comes in, the dispatcher checks a board showing where all ambulances are right now (Redis). They pick the nearest available ambulance, radio the crew (push notification), wait for them to accept (driver accept), and then track the ambulance live on a map until arrival. The board updates every few seconds automatically. That is the entire ride-sharing dispatch system.

### Full HLD diagram

```
[Rider App]          [Driver App]
     |                    |
     | request ride       | location ping (every 4s)
     |                    |
     v                    v
+------------------------------------------+
|              API GATEWAY                 |
|    Auth (JWT), Rate limiting, Routing    |
+------------------------------------------+
         |              |
         v              v
+-------------+   +------------------+
| MATCHING    |   | LOCATION SERVICE |
| SERVICE     |   |                  |
|             |   | - validates ping |
| 1. GEORADIUS|   | - GEOADD to Redis|
| 2. rank     |   | - async -> Kafka |
| 3. offer    |   +------------------+
| 4. retry    |          |
+-------------+          v
     |              +----------+
     |              | REDIS    |
     |              | GEO      |
     |              | (per city|
     |<-------------+ instance)|
     |              +----------+
     v
+----------+          +----------+
| TRIP     |          | KAFKA    |
| SERVICE  |--------->| TOPICS   |
|          |          |          |
| State    |          | location-|
| machine  |          | updates  |
| Postgres |          | trip-    |
+----------+          | events   |
     |                +----------+
     v                     |
+----------+     +---------+---------+
| NOTIF.   |     |                   |
| SERVICE  |     v                   v
|          | +----------+     +----------+
| Push to  | | PRICING  |     | ANALYTICS|
| driver:  | | SERVICE  |     | SERVICE  |
| accepted |  +----------+    +----------+
| Push to  |
| rider:   |
| matched  |
+----------+
```

### Component responsibilities

```
+------------------+-----------------------------------+-----------+------------------+
| Component        | Responsibility                    | Stateful? | Scale target     |
+------------------+-----------------------------------+-----------+------------------+
| Location Service | Receives driver pings, validates, | NO        | 250K writes/sec  |
|                  | GEOADD to Redis, async Kafka pub  |           | 10 instances     |
+------------------+-----------------------------------+-----------+------------------+
| Redis Geo        | Live driver location index        | YES       | 70 MB (1M driver)|
| (per city shard) | GEOADD/GEORADIUS queries          |           | 1 instance/city  |
+------------------+-----------------------------------+-----------+------------------+
| Matching Service | GEORADIUS -> rank -> offer ->     | NO        | 350 requests/sec |
|                  | handle accept/reject              |           | 3 instances      |
+------------------+-----------------------------------+-----------+------------------+
| Trip Service     | Trip state machine, persists to   | NO        | 350 trips/sec    |
|                  | Postgres, publishes events        |           | 3 instances      |
+------------------+-----------------------------------+-----------+------------------+
| Postgres         | Trips, fare records, driver state | YES       | 350 writes/sec   |
| (trips DB)       | Source of truth for trip history  |           | 1 primary + 2 RR |
+------------------+-----------------------------------+-----------+------------------+
| Cassandra        | Driver location history           | YES       | 250K writes/sec  |
|                  | Audit trail, trip replay          |           | 5 nodes          |
+------------------+-----------------------------------+-----------+------------------+
| Notification Svc | Push to driver/rider apps         | YES       | 1M WebSockets    |
|                  | APNs/FCM for mobile               |           |                  |
+------------------+-----------------------------------+-----------+------------------+
| Kafka            | Location stream, trip event stream| YES       | 250K + 1K msg/s  |
|                  | Decouples real-time from analytics|           | RF=3             |
+------------------+-----------------------------------+-----------+------------------+
| Pricing Service  | Computes surge multiplier per geo | NO        | 350 requests/sec |
|                  | cell; calculates final fare       |           | 1 instance       |
+------------------+-----------------------------------+-----------+------------------+
```

---

## Component 1: Driver Location Tracking — The Hot Write Path

**This is the single most important component. Nail this and the rest follows.**

### Why Redis Geo, not a relational DB

```
Naive approach: store driver location in Postgres.
  UPDATE drivers SET lat=40.7128, lng=-74.0060, updated_at=NOW() WHERE driver_id='d123'
  
  At 250K updates/sec:
    Postgres: max ~10K-30K writes/sec on a modern instance
    250K / 30K = 8-9 Postgres instances needed just for location
    And: the read query is worse —
    SELECT driver_id FROM drivers WHERE ST_DWithin(location, rider_point, 5000)
    PostGIS geospatial query on 80K rows (NYC drivers): full geospatial index scan
    At 350 queries/sec: feasible but expensive. p99 may spike.

Redis GEOADD:
  GEOADD drivers:nyc -74.0060 40.7128 "d123"
  O(log N) per update. In-memory. No disk I/O.
  250K GEOADD/sec per city shard: within Redis capacity.

Redis GEORADIUS (deprecated; use GEOSEARCH since Redis 6.2):
  GEOSEARCH drivers:nyc FROMLONLAT -74.0050 40.7100 BYRADIUS 5 km ASC COUNT 10 WITHCOORD WITHDIST
  Returns: up to 10 nearest drivers within 5km, sorted by distance, with coordinates and distance.
  O(N + log N) where N is the search area. For 5km radius in NYC with 80K drivers:
    80K * (5km / city_radius)^2 = fraction of drivers in 5km area -> O(hundreds of drivers) to scan.
  Latency: 1-5ms in practice for a 5km radius search.
```

### How Redis Geo works internally

```
Redis GEO is built on top of Redis Sorted Set (ZSET).
The score for each member is a 52-bit GeoHash of the (lat, lng) coordinates.

GeoHash encoding:
  1. Normalize lat to [-90, 90] and lng to [-180, 180].
  2. Interleave bits: lng_bit_0, lat_bit_0, lng_bit_1, lat_bit_1, ...
  3. This interleaving encodes 2D proximity into a 1D number.
  4. Points that are geographically close have similar GeoHash values.
  5. Store as ZSET score (a double).

GEORADIUS/GEOSEARCH algorithm:
  1. Convert the search center (lat, lng) to a GeoHash.
  2. Find the GeoHash cell that contains the center.
  3. Search the cell + 8 neighboring cells (3x3 grid around center).
  4. For all members in those cells: compute actual distance.
  5. Filter by radius. Sort by distance. Return top N.
  
  This is a ZSET range scan on hash values (step 3) + distance filter (step 4).
  Efficient because GeoHash locality = ZSET score locality = B-tree range scan.

Precision:
  52-bit GeoHash in Redis: ~0.6m precision (60 cm). More than enough for ride matching.
  At the equator, 1 degree latitude = 111km. With 52 bits: 111km / 2^26 = 0.00165m precision.
```

### Location update pipeline

Each driver ping flows through four quick steps: (1) HTTP POST to Location Service (fire-and-forget — driver does not wait for acknowledgment); (2) Location Service validates the coordinates (lat/lng in range, speed < 300 km/h) and calls `GEOADD available_drivers:{city} lng lat driver_id`; (3) async publish to Kafka topic `location-updates` keyed by `driver_id` (ensures per-driver ordering), consumed by Cassandra writer, Analytics, and Active Trip Tracker; (4) 204 returned immediately — Kafka publish does not block the response. Total round-trip: 10-30ms.

---

## Component 2: Driver Matching — Finding the Best Driver

### The matching algorithm

Matching runs in seven logical steps after a rider confirms:

1. **Request created** — Trip Service inserts a REQUESTED record in Postgres and publishes to Kafka.
2. **Price estimate** — Pricing Service reads `GET surge:{h3_cell}` from Redis; returns `surge_multiplier` to rider before confirmation. Surge is locked at confirmation time.
3. **GEOSEARCH** — `GEOSEARCH available_drivers:nyc FROMLONLAT lng lat BYRADIUS 5 km ASC COUNT 20 WITHCOORD WITHDIST`. Returns up to 20 nearest available drivers. Expand to 10km if count < 3.
4. **Rank candidates** — For each candidate: read `driver_rating:{driver_id}` from Redis cache; batch-call Google Maps Distance Matrix API for ETA (one API call for all 5 top candidates). Score = `0.6 * norm_distance + 0.2 * norm_rating + 0.2 * norm_eta`. Sort descending.
5. **Offer top driver** — `SET offer:{trip_id} driver_1_id EX 10`. Push notification via FCM/APNs. Simultaneously claim the driver via the Lua atomic script (see Component 2 — Atomic State Transition below).
6. **Wait for response** — Await driver accept/reject via WebSocket (foreground) or push-notification webhook (background). 10-second window.
7. **Accept or retry** — On ACCEPT: `UPDATE trips SET status='MATCHED', driver_id=? WHERE trip_id=? AND status='REQUESTED'` (optimistic lock). Notify rider. On REJECT or TIMEOUT: offer to driver_2. Max 5 attempts before trip fails.

### Driver availability state machine

Driver state is stored in two places: Redis (fast, TTL-gated) and Postgres (durable for analytics). Redis is authoritative for matching; Postgres is authoritative for history.

**States:**

| State | Description | In available ZSET? |
|-------|-------------|-------------------|
| OFFLINE | Not broadcasting; not eligible for offers | No |
| AVAILABLE | Pinging; eligible for offers | Yes |
| OFFERED | Received offer; 10-second window | No (removed atomically) |
| EN_ROUTE | Accepted trip; driving to pickup | No |
| ON_TRIP | Rider in car; en route to destination | No |
| COMPLETING | Trip ended; fare processing in progress | No |

**TTL heartbeat:** every location ping executes `SET driver_state:{driver_id} "AVAILABLE" EX 30`. If the driver's app crashes, pings stop, and after 30 seconds the key expires — the driver silently leaves the available pool. No explicit offline event needed.

**Transitions:**
- OFFLINE -> AVAILABLE: driver taps "Go Online"
- AVAILABLE -> OFFERED: matching service runs Lua atomic script (see Incident 4 and Exercise 2 for the exact script)
- OFFERED -> EN_ROUTE: driver accepts; trip MATCHED
- OFFERED -> AVAILABLE: driver rejects or 10-second window times out; `GEOADD` back to available ZSET
- EN_ROUTE -> ON_TRIP: driver confirms pickup arrival
- ON_TRIP -> COMPLETING: driver ends trip
- COMPLETING -> AVAILABLE: fare posted; driver re-enters pool

---

## Component 3: Trip State Machine

### Trip states and transitions

```
REQUESTED -> MATCHED -> DRIVER_EN_ROUTE -> RIDER_PICKED_UP -> COMPLETED
     ^               |                                    |
     |               v                                    v
   FAILED        CANCELLED                          CANCELLED_BY_DRIVER
```

State is stored in Postgres (authoritative, queryable) and cached in Redis for active trip reads. Full schema is in the DB Schema section below. Every transition is an idempotent `UPDATE trips SET status='NEW' WHERE trip_id=? AND status='EXPECTED'` — if `rows_affected=0`, the event is a duplicate and is safely ignored.

### Kafka event stream

Topic `trip-events`, partitioned by `trip_id` (guarantees per-trip ordering). Each state transition publishes one event: `{trip_id, event, ts, ...relevant fields}`. Events include REQUESTED, MATCHED, EN_ROUTE, PICKED_UP, COMPLETED, CANCELLED.

Consumer groups and their responsibilities:
- **Notification Service** — MATCHED: push "Driver found" to rider; EN_ROUTE: start live location feed; COMPLETED: show receipt.
- **Pricing Service** — COMPLETED: compute final fare (distance + time + surge locked at start); write `fare_cents` to trips table.
- **Driver Earnings Service** — COMPLETED: credit driver's balance (idempotent: ON CONFLICT DO NOTHING on trip_id).
- **Analytics Service** — ALL events: write to data warehouse for business dashboards.
- **Fraud Service** — COMPLETED: pull driver's Cassandra location history; check for impossible speeds, GPS jumps, detour ratio.

Each consumer group maintains its own offset — a Notification Service restart resumes without affecting Pricing Service consumption.

---

## Component 4: Live Trip Tracking

**"How does the rider see the driver's dot moving on a map?"**

### Architecture

The driver already sends a location ping every 4 seconds. The Trip Tracking Service (a Kafka consumer) reads from the `location-updates` topic, checks `GET driver_active_trip:{driver_id}` in Redis, and if a trip is active, pushes the new coordinates to the rider's WebSocket connection (`GET rider_ws:{rider_id}` -> which WebSocket server node holds that rider's connection). The rider's app receives the push and re-renders the driver dot. Update rate: every 4 seconds, matching the driver's ping rate.

**Why push over polling:** 313K active trips polling every 4 seconds = 78K Redis reads/sec just for rider-side location. WebSocket push eliminates those reads — the server controls when updates are sent. Server-side rate limiting also prevents the Notification Service from being overwhelmed if a city has an unusual spike in active trips.

---

## Component 5: Surge Pricing

### The supply/demand signal

```
Surge zone: a hexagonal geo-cell (Uber uses H3 library: Uber's own hexagonal grid).
  H3 resolution 8: hexagons ~0.7km wide. NYC: ~5000 hexagons cover the city.

Every 5 minutes, Surge Pricing Service:
  Step 1: Count ride requests per H3 cell in the last 5 minutes.
    SELECT h3_cell, COUNT(*) FROM ride_requests
    WHERE requested_at > NOW() - INTERVAL '5 minutes'
    GROUP BY h3_cell
    Source: Kafka consumer writes requests to a Redis counter per cell.
    INCR demand_count:{h3_cell}:{window} EX 300  (auto-expire after 5 minutes)

  Step 2: Count available drivers per H3 cell (from Redis Geo).
    GEOSEARCH available_drivers:nyc ... per cell
    Or: maintain a separate counter: INCR supply_count:{h3_cell} on driver enter cell, DECR on leave.

  Step 3: Compute surge multiplier.
    demand = demand_count:{h3_cell}
    supply = supply_count:{h3_cell}
    ratio = demand / max(supply, 1)
    
    multiplier:
      ratio < 0.5: 1.0x (no surge)
      0.5 to 1.0: 1.2x
      1.0 to 2.0: 1.5x
      2.0 to 3.0: 2.0x
      > 3.0:      2.5x (cap)
  
  Step 4: Store multiplier in Redis.
    SET surge:{h3_cell} 1.5 EX 300  (valid for 5 minutes)
  
  Step 5: On ride request, apply multiplier.
    h3_cell = lat_lng_to_h3(rider_lat, rider_lng, resolution=8)
    surge = GET surge:{h3_cell} or 1.0 (default)
    estimated_price = (base_fare + distance * rate) * surge

Display:
  Before rider confirms: show surge multiplier prominently.
  Show countdown timer: "Surge pricing ends in 3:42"
  Legal requirement in some cities: rider must explicitly confirm surge pricing.
```

---

## API Design

These are the five endpoints an interviewer is most likely to ask you to sketch. Knowing the request/response shape, the status codes, and the one-sentence "Notes" line for each demonstrates that you understand the full round-trip, not just the backend component.

### Request a Ride (Rider)

```
POST /v1/rides
Request:  { rider_id: string, pickup: {lat, lng}, dropoff: {lat, lng},
            ride_type: ECONOMY|POOL|XL }
Response: { trip_id: string, status: REQUESTED, eta_seconds: int,
            surge_multiplier: float }
Notes:    Creates trip in REQUESTED state; matching is async via Kafka.
          surge_multiplier is locked at this moment — rider sees it before confirming.
          Returns immediately (< 200ms); matching continues in background.
Errors:   429 if rider has an active trip already (idempotency guard)
          503 if no drivers available in the expanded 10km radius
```

### Accept Ride (Driver)

```
POST /v1/rides/{trip_id}/accept
Request:  { driver_id: string }
Response: { trip_id: string, status: MATCHED, rider_pickup: {lat, lng},
            rider_name: string }
Errors:   409 Conflict if trip already matched by another driver
          (race condition: Lua script returned 0; driver retries offer queue)
          404 if offer window expired (10-second timeout)
Notes:    On success, Matching Service runs the Redis Lua AVAILABLE->OFFERED script.
          Trip Service writes MATCHED to Postgres. Kafka publishes MATCHED event.
```

### Update Driver Location

```
PUT /v1/drivers/{driver_id}/location
Request:  { lat: float, lng: float, heading: float, speed: float }
Response: 204 No Content
Notes:    Called every 4 seconds by driver app. Fire-and-forget — driver does not
          wait for acknowledgment.
          Feeds Redis GEOADD for available_drivers:{city} ZSET.
          NOT stored in Postgres — current location lives in Redis only.
          History written async to Cassandra via Kafka consumer.
Validation: 400 if speed > 300 km/h or lat/lng out of range (sanity check)
```

### Complete Trip

```
POST /v1/rides/{trip_id}/complete
Request:  { driver_id: string, final_location: {lat, lng} }
Response: { trip_id: string, status: COMPLETED,
            fare: { amount_cents: int, currency: string, surge_multiplier: float } }
Notes:    Triggers fare calculation (base + per-mile + per-minute) * surge_locked_at_start.
          Publishes COMPLETED event to Kafka.
          Pricing Service computes fare; Driver Earnings Service credits driver.
          Payment Service charges rider (async, saga pattern — see Ch58).
          Driver state transitions: COMPLETING -> AVAILABLE after fare is posted.
Errors:   403 if driver_id does not match the trip's assigned driver
          409 if trip is already in COMPLETED or CANCELLED state
```

### Get ETA

```
GET /v1/rides/{trip_id}/eta
Response: { eta_seconds: int, driver_location: {lat, lng}, distance_meters: int }
Notes:    Reads driver location from Redis (GET driver_location:{driver_id}).
          ETA computed from Google Maps Distance Matrix API or in-house ML model.
          p99 < 100ms (Redis read is < 1ms; Maps API call is the tail latency).
          Called by rider app every 10-15 seconds during EN_ROUTE phase
          (not every 4s — the WebSocket push handles the live dot; this is for ETA text).
Errors:   404 if trip_id does not exist or is not in an active state
```

---

## DB Schema

These are the four tables that matter for the core dispatch system. The schema choices here — what goes in Postgres, what stays in Redis only, which indexes are partial — are exactly the kind of detail that separates L5 from L4 in an interview.

```sql
CREATE TABLE trips (
  trip_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  rider_id         UUID         NOT NULL,
  driver_id        UUID,                              -- null until MATCHED
  status           VARCHAR(20)  NOT NULL,             -- REQUESTED|MATCHED|EN_ROUTE|PICKED_UP|COMPLETED|CANCELLED
  pickup_lat       DECIMAL(9,6) NOT NULL,
  pickup_lng       DECIMAL(9,6) NOT NULL,
  dropoff_lat      DECIMAL(9,6) NOT NULL,
  dropoff_lng      DECIMAL(9,6) NOT NULL,
  surge_multiplier DECIMAL(4,2) NOT NULL DEFAULT 1.0, -- locked at rider confirmation time
  fare_cents       INT,                               -- null until COMPLETED
  requested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  matched_at       TIMESTAMPTZ,
  picked_up_at     TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ
);

-- Rider history: "show me my past trips" — scoped to one rider, newest first
CREATE INDEX idx_trips_rider  ON trips(rider_id, requested_at DESC);
-- Driver history: "show me my completed trips this week" — scoped to one driver
CREATE INDEX idx_trips_driver ON trips(driver_id, requested_at DESC);
-- Active trip dashboard: only non-terminal states — partial index keeps it tiny
CREATE INDEX idx_trips_status ON trips(status) WHERE status NOT IN ('COMPLETED','CANCELLED');

-- Why DECIMAL(9,6) for lat/lng: 6 decimal places = ~0.11m precision. Enough for GPS.
-- Why not FLOAT: FLOAT rounding errors accumulate in distance calculations.
-- Why not store current location here: driver location changes 250K times/sec globally.
--   Postgres cannot absorb 250K UPDATE/sec. Redis can. Location lives in Redis only.
```

```sql
CREATE TABLE drivers (
  driver_id      UUID         PRIMARY KEY,
  name           TEXT         NOT NULL,
  vehicle_type   VARCHAR(20)  NOT NULL,              -- ECONOMY|XL|COMFORT|BLACK
  rating         DECIMAL(3,2) NOT NULL DEFAULT 5.0,
  is_active      BOOLEAN      NOT NULL DEFAULT false  -- background-checked and approved
  -- current_lat, current_lng NOT stored here
  -- Redis key: geo:available_drivers:{city_id} (GEOADD)
  -- Redis key: driver_state:{driver_id}  (AVAILABLE|OFFERED|EN_ROUTE|ON_TRIP|COMPLETING)
  -- Redis key: driver_rating:{driver_id} (cached rating for fast matching rank)
);
-- No location columns in Postgres. All real-time location is Redis-only.
-- Rating cached in Redis: SET driver_rating:{driver_id} 4.87
-- Refreshed after each trip completion by Driver Earnings Service.
```

```sql
CREATE TABLE driver_earnings (
  id             BIGSERIAL    PRIMARY KEY,
  driver_id      UUID         NOT NULL,
  trip_id        UUID         NOT NULL UNIQUE,        -- idempotency: one row per trip
  gross_fare_cents INT        NOT NULL,
  commission_cents INT        NOT NULL,               -- platform fee (20-25%)
  net_earnings_cents INT      NOT NULL,               -- gross - commission
  guarantee_topup_cents INT   NOT NULL DEFAULT 0,     -- weekly guarantee program top-up
  earned_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_earnings_driver ON driver_earnings(driver_id, earned_at DESC);
-- UNIQUE on trip_id: ON CONFLICT (trip_id) DO NOTHING makes the insert idempotent.
-- If the COMPLETED Kafka event is processed twice, the second insert is a no-op.
-- This is the idempotency key pattern — trip_id is both the business key and the dedup key.
```

```sql
-- Surge pricing derived table
-- Written by Pricing Service (every 5 minutes), read by Matching Service at request time.
-- This is a materialized snapshot — the live multiplier is in Redis; this is for audit/replay.
CREATE TABLE surge_zones (
  h3_index       VARCHAR(20)  PRIMARY KEY,  -- H3 hex cell ID at resolution 7 (~5km wide)
  city_id        VARCHAR(20)  NOT NULL,
  multiplier     DECIMAL(4,2) NOT NULL,
  demand_count   INT          NOT NULL,     -- ride requests in last 5 min
  supply_count   INT          NOT NULL,     -- available drivers in cell at calculation time
  updated_at     TIMESTAMPTZ  NOT NULL
);
CREATE INDEX idx_surge_city ON surge_zones(city_id, updated_at DESC);
-- The live multiplier is cached in Redis: SET surge:{city}:{h3_index} 1.5 EX 330
-- This table is the audit trail: "what was the surge in Times Square at 6 PM on Friday?"
-- Used for: dispute resolution, regulatory reporting, pricing model validation.
-- H3 resolution 7: ~5km wide cells — coarse enough for surge pricing signal,
-- fine enough that NYC has ~200 cells (manageable query cardinality).
-- Do not confuse with resolution 9 (~0.5km) used for routing precision.
```

**Schema design decisions to mention in an interview:**

- `trips.driver_id` is nullable: the trip exists before a driver is assigned. Inserting with `driver_id = NULL` and updating it when matched avoids a two-step insert/update that could fail between.
- `driver_earnings.trip_id UNIQUE`: this is the idempotency key. Re-processing a COMPLETED Kafka event does not double-credit the driver.
- No `drivers.current_lat/lng`: current location is Redis-only. Adding it to Postgres would require 250K UPDATE/sec globally — Postgres cannot handle that write rate.
- Partial index on `trips(status)` excludes COMPLETED and CANCELLED rows: the index stays small (only active trips) so the Matching Service's active-trip lookup stays fast even after millions of historical trips accumulate.

---

## Failure Scenarios

### Failure 1: City Redis instance crashes (location index lost)

```
Impact:
  - All drivers in that city: location index lost. GEORADIUS returns empty.
  - New ride requests in that city: no drivers found. Match fails.
  - Active trips: drivers still broadcasting to the crashed Redis. Updates lost.
    (Active trips tracked in Postgres/Kafka — trip status unaffected.)

Recovery:
  Redis restarts from RDB snapshot (last 5 minutes of data).
  Missing: up to 5 minutes of location updates since snapshot.
  Drivers automatically re-populate via their 4-second pings.
  Within 30-60 seconds: most online drivers have pinged and are back in the index.

Degraded mode during 30-60s recovery:
  Option A: expand search to neighboring city's Redis (if cities overlap geographically).
  Option B: serve from Cassandra (last known location per driver, queried directly).
    SELECT lat, lng FROM driver_locations WHERE driver_id = ? ORDER BY ts DESC LIMIT 1
    For matching: batch query for all known drivers in the area.
    This is expensive (N DB reads instead of 1 Redis geo query) but prevents full outage.

Prevention:
  Redis persistence: RDB every 1 minute (more frequent than default).
  Redis replica: promote within 10 seconds. Replica lag < 10 seconds (recent locations only).
  Read from replica during failover: slightly stale locations (acceptable for matching).
```

### Failure 2: Driver misses the offer (app in background, notification delayed)

```
Scenario: Matching Service sends push notification to driver.
  FCM delivers it 8 seconds later (FCM delay).
  Driver sees the offer for 2 seconds before the 10-second window expires.
  Driver taps accept at T=10.1s. Too late. Offer already expired.
  System offered the trip to driver_2. Driver_2 accepted.
  Driver_1 sees "trip assigned to another driver" — confusing.

Impact: driver frustration. Wasted time.

Fix:
  Extend offer window to 15 seconds for drivers who are known to have slow FCM delivery.
  Track per-driver FCM delivery latency. If avg > 5s, use 15s window.
  
  Alternatively: client-side offer management.
  Instead of a 10-second server timeout, driver app shows the offer and sends accept via:
    - FCM (push): for app-in-background
    - WebSocket (if app in foreground): instant response
  Server waits for whichever arrives first.
```

### Failure 3: Driver app GPS spoofing (fraud)

```
Scenario: a driver runs a GPS spoofing app to appear near high-demand areas.
  Fraudulently collects surge-priced rides from areas where they are not physically present.
  Or: the driver takes a detour to inflate the fare (longer route).

Detection (runs as post-trip analysis, not real-time):
  Compare reported GPS route with expected route (Google Maps optimal route).
  Flag: if reported distance > 1.3x Google Maps distance.
  Flag: if reported speed at any point > 200 km/h (physically impossible).
  Flag: if driver location jumps by > 1km in 4 seconds (GPS spoof artifact).
  
  Compute on Cassandra: SELECT * FROM driver_locations WHERE driver_id = ? AND ts BETWEEN pickup_at AND dropoff_at
  Apply physics checks to the route.

Action: flag for fraud review. If confirmed: deactivate driver account.

Real-time prevention:
  Speed sanity check in Location Service: if speed > 200 km/h, reject the ping.
  Kalman filter: smooth GPS trajectory. Jumps that violate physics are rejected.
```

### Failure 4: Matching service overload during rain storm (demand spike)

```
Scenario: heavy rain starts in NYC at 5 PM rush hour.
  Ride requests spike 10x normal: 3,470 requests/sec instead of 347.
  
  Matching Service at 3x normal instances: 347 * 3 = 1,041 requests/sec capacity.
  At 3,470/sec: 3x overload. Request queues grow. Latency spikes.

Immediate mitigation:
  Auto-scaling: Matching Service instances scale from 3 to 30 (30-second spin-up).
  During the 30-second scale-up: request queue in Kafka buffers the requests.
  Kafka topic: ride-requests. Consumers: Matching Service instances.
  
  As more Matching Service instances come up: they consume from Kafka and process requests.
  Latency: ride request processing delayed by 30-120 seconds during the storm.
  SLA degradation: matching latency goes from 12s to 2-3 minutes. Acceptable in a storm.

Surge pricing effect (self-regulating):
  High demand activates surge pricing. Higher prices reduce rider demand.
  Also: higher prices attract more drivers (higher earnings). More supply.
  Surge pricing is the market mechanism that self-regulates during spikes.
  A 2x surge typically reduces demand by 30-40% and increases supply by 20-30%.
  Net result: demand/supply ratio normalizes within 10-15 minutes of surge activation.
```

---

## Deep Concept Explanations

### Concept 1: GeoHash and Why Geospatial Indexing Works

```
Problem: given a point (40.7128, -74.0060), find all points within 5km.
Naive SQL: SELECT * FROM drivers WHERE sqrt((lat-40.7128)^2 + (lng+74.0060)^2) < 0.045
  Full table scan. O(N). Catastrophic at 80K rows queried 350 times/sec.

B-tree index on lat: SELECT * FROM drivers WHERE lat BETWEEN 40.66 AND 40.76
  Narrows to a horizontal band. Still returns too many rows (the whole city).
  Cannot combine lat AND lng efficiently in one B-tree.

GeoHash encodes 2D into 1D:
  The key insight is bit-interleaving: take the binary representation of latitude
  and longitude and interleave the bits.
  
  Example:
    lat = 40.7128 -> normalized to [0,1]: 0.724 -> binary: 0.10111001...
    lng = -74.006 -> normalized to [0,1]: 0.289 -> binary: 0.01001011...
    
    Interleaved (lng bit, lat bit, lng bit, lat bit...):
    0,1,0,1,0,0,0,1,1,0,0,1...

  Properties of the interleaved number:
    - Points close in 2D space are close in the 1D number line (with exceptions at boundaries)
    - A prefix of the interleaved bits defines a rectangular region
    - Two points in the same region have the same prefix

  Redis encodes this interleaved number as a 52-bit integer stored as a ZSET score.
  GEORADIUS/GEOSEARCH: find the score range for the search area, do a ZSET range scan.
  Filter: check each candidate's actual distance (Haversine formula).

Why cells + 8 neighbors:
  The 5km search area might span multiple GeoHash cells.
  Searching just the center cell misses drivers in neighboring cells.
  Searching 9 cells (3x3 grid) guarantees all drivers within the radius are found.
  (May include some extra drivers in the corners of the 3x3 that are farther than 5km,
   but those are filtered by the exact distance check.)
```

### Concept 2: Consistent Hashing for Driver Shards

```
Problem: as the service grows globally, you add more Redis instances (shards).
  Adding or removing a shard invalidates all existing routing:
  City -> Redis shard mapping must be reconfigured.
  Simpler: hash(driver_lat_lng) % num_shards.
  But: adding one shard remaps almost all drivers to new shards.
  During remapping: drivers are temporarily "lost" (old Redis has them, new Redis does not).

Solution: consistent hashing.
  Arrange shard IDs on a ring from 0 to 2^32.
  Each Redis instance has N "virtual nodes" on the ring (N=100-200).
  Each driver's location maps to a hash value -> falls between two virtual nodes -> assigned to that shard.
  
  Adding one new Redis shard: only the drivers between the new shard's virtual nodes and the
  previous neighbor are remapped. ~1/num_shards fraction of drivers.
  
  For ride sharing, a simpler approach works: geo-based partitioning.
  Each city gets its own Redis instance. Routing is by city (not hash).
  Consistent hashing is needed only if a single city has too many drivers for one Redis instance
  (a London Redis instance with 200K drivers), requiring sub-city sharding.
  
  Sub-city sharding: divide the city into N geographic quadrants.
  Each quadrant's drivers go to a different Redis shard.
  A 5km radius search hits at most 4 quadrants (worst case: search center at the corner of 4 quadrants).
  4 parallel GEORADIUS queries (one per quadrant Redis) + merge results.
```

### Concept 3: ETA Accuracy and Its Effect on Matching

```
The matching algorithm ranks drivers by: distance + ETA + rating.
ETA accuracy matters: if ETA is wrong, riders get frustrated (driver arrives 5min later than promised).

Simple ETA: straight-line distance / average speed
  Speed = 30 km/h for city driving
  Distance = 0.8 km
  ETA = 0.8 / 30 = 1.6 minutes
  Problem: doesn't account for traffic, one-way streets, construction.

Google Maps Directions API: most accurate.
  Input: driver location + pickup location
  Output: ETA accounting for live traffic
  Cost: ~$5 per 1000 requests. At 350 matches/sec * 20 candidates * $5/1000 = $175/sec = $15M/day.
  Too expensive to call for every candidate.

Optimization: call Maps API only for the top 3-5 candidates (after distance filtering).
  Distance sort is free (GEORADIUS result). Maps API only for the final ranking.
  350 requests/sec * 5 Maps calls = 1750 Maps calls/sec = $0.875/sec = $75K/day. Still expensive.

Better: Google Maps Distance Matrix API (batch).
  One API call: [origin_1, origin_2, ..., origin_5] -> [rider_pickup]
  One API call for 5 drivers instead of 5 separate calls. 5x cost savings.

Best (L6): train an in-house ETA prediction model.
  Features: driver location, pickup location, time of day, day of week, weather, historical traffic.
  Model: gradient boosted tree or a lightweight neural net.
  Latency: <5ms (much faster than external API call: 50-200ms).
  Cost: infra for model serving, but no per-call API fee.
  Uber, Lyft, DoorDash all have in-house ETA models.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+-----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)              | L6 (Staff)                     |
+---------------------+-----------------------------+--------------------------------+
| Location tracking   | Redis GEOADD, 250K writes/  | City-partitioned Redis shards. |
|                     | sec, why not Postgres        | Sub-city consistent hashing    |
|                     |                             | for metropolises. Explains     |
|                     |                             | GeoHash bit-interleaving.      |
+---------------------+-----------------------------+--------------------------------+
| Matching algorithm  | GEORADIUS top-10, rank by   | ETA prediction model vs Maps   |
|                     | distance + rating            | API cost analysis. Batched     |
|                     |                             | Distance Matrix API. Driver    |
|                     |                             | accept race condition fix      |
|                     |                             | (compare-and-swap in Redis).   |
+---------------------+-----------------------------+--------------------------------+
| Driver availability | Redis state + DB state,     | TTL on Redis state = auto-     |
|                     | ZREM from available ZSET    | offline on ping stop. Dual-    |
|                     | on offer                    | write (Redis + Postgres) with  |
|                     |                             | Cassandra as reconciliation    |
|                     |                             | source of truth.               |
+---------------------+-----------------------------+--------------------------------+
| Trip state machine  | Knows all states and        | Kafka partition key = trip_id  |
|                     | transitions, Kafka events   | for ordering. At-least-once    |
|                     |                             | delivery: idempotent state     |
|                     |                             | transitions (SET status WHERE  |
|                     |                             | status='PREVIOUS_STATE').      |
+---------------------+-----------------------------+--------------------------------+
| Surge pricing       | Demand/supply ratio per     | H3 hexagonal cells (why hexa- |
|                     | geo-cell, multiplier tiers  | gon not grid). Smoothing at    |
|                     |                             | cell boundaries (rider at edge |
|                     |                             | of surge zone). Rider consent  |
|                     |                             | legal requirements.            |
+---------------------+-----------------------------+--------------------------------+
| Live tracking       | Driver pings -> Kafka ->    | Per-trip WebSocket namespace   |
|                     | push to rider WebSocket      | (each trip has own channel).   |
|                     |                             | Backpressure on notification   |
|                     |                             | service (rate-limit pushes to  |
|                     |                             | 1/4s even if Kafka has more).  |
+---------------------+-----------------------------+--------------------------------+
| Failure handling    | Redis crash -> rebuilds     | Active trip during Redis fail- |
|                     | from driver pings           | over: switch to Cassandra read  |
|                     |                             | for driver location. Rider     |
|                     |                             | sees 30-60s stale location     |
|                     |                             | during failover. Acceptable.   |
+---------------------+-----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Uber "Surge Pricing at Wrong Location" Bug (2016)

**Company:** Uber  
**What happened:** Uber used the rider's pickup location to determine the surge zone. In Times Square, the H3 cells are small (~500m diameter). A rider standing at the edge of a 2.0x surge zone and a 1.0x no-surge zone saw 2.0x pricing if their GPS jittered by 100m. Riders standing in physically the same location got different prices based on GPS noise. Complaint volume spiked.

**Root cause:** Hard cutoff at cell boundary. A rider at position A (2.0x cell) and position B (1.0x cell) with A-B = 50 meters got a 2x price difference.

**Fix:** Applied smoothing at cell boundaries. When a rider is within 200m of a cell boundary, compute a weighted average of the two neighboring cells' surge multipliers based on distance from the boundary. Rider at exactly the boundary: exactly the average of both cells' multipliers.

**Staff lesson:** Discrete zone boundaries in continuous space create UX cliffs. Any time you partition continuous geography into discrete cells (surge zones, service areas, pricing tiers), design for smooth transitions at boundaries. A 50-meter step difference in price is a customer complaint. A smooth ramp is forgettable.

---

### Incident 2: Lyft Driver Location Index Corruption (2018)

**Company:** Lyft  
**What happened:** A deployment error caused the Location Service to write driver locations to the wrong Redis key (`available_drivers:all` instead of `available_drivers:{city}`). Within 10 minutes, all drivers globally were mixed into a single ZSET. GEORADIUS queries for NYC returned drivers in LA, Tokyo, and London as "nearby." Match quality collapsed. For 45 minutes, Lyft's dispatch matched riders with drivers 10,000 km away. All matches failed when drivers obviously could not reach riders.

**Root cause:** A config change replaced `{city}` template with a hardcoded `all` key. The deployment passed config validation (the key was valid, just wrong). Integration tests did not verify geospatial correctness of matches.

**Fix:**
- Added a post-deployment canary check: after each deployment, verify that GEORADIUS for NYC only returns drivers with coordinates within 100km of NYC.
- Added match sanity check: if matched driver's current location is more than 100km from rider, reject the match (impossible pickup) and alert.
- Config templating validation: city key must be a known city identifier from a whitelist.

**Staff lesson:** Geographic correctness is hard to test. Unit tests don't catch "driver is in wrong city." Add post-deployment integration canaries that check domain-level invariants: "every matched driver should be within N km of the rider."

---

### Incident 3: Uber Thundering Herd on Redis Reconnect (2017)

**Company:** Uber  
**What happened:** A Redis instance serving 60K drivers (NYC) crashed and restarted after a 90-second outage. On restart, all 60K drivers' apps reconnected and attempted GEOADD simultaneously — 60K * 250 pings/driver/hour = 15K GEOADD/sec, all arriving within a 10-second window as the apps reconnected. Redis: saturated immediately on restart. Latency spiked to 5 seconds. Redis crashed again from the load.

**Root cause:** All apps reconnect at the same time (thundering herd). No backoff on reconnect. The reconnect storm itself caused a second crash, creating a crash loop.

**Fix:**
- Added jittered exponential backoff to all Location Service clients: on Redis connection failure, wait `rand(1, min(2^attempt, 60))` seconds before retry.
- Added a startup rate limiter in Redis proxy: accepts at most 5K connections/second on startup. Queues the rest.
- Pre-warmed the Redis instance: before promoting the replica or restarting, apply a connection token bucket so initial traffic is throttled.

**Staff lesson:** Systems that crash cause reconnection thundering herds that cause crashes again. Any component that multiple clients connect to needs reconnect jitter baked into every client. This is especially critical for real-time systems where all clients notice a failure simultaneously.

---

### Incident 4: Driver State Inconsistency During Matching Race (2019)

**Company:** Lyft  
**What happened:** Two Matching Service instances simultaneously offered the same driver to two different riders. Both riders were shown "driver found." Both were notified of the same driver. The driver received two trip offers. They accepted one. The other rider's trip remained in MATCHED state with no actual driver. That rider waited 15 minutes before the trip auto-cancelled.

**Root cause:** The AVAILABLE -> OFFERED transition (remove from available ZSET, set state to OFFERED) was not atomic. Two matching service instances both read the driver as AVAILABLE from Redis, both sent offers, both removed the driver from the ZSET (ZREM is idempotent), both set state to OFFERED. No conflict detected.

**Fix:** Made the AVAILABLE -> OFFERED transition atomic using a Redis Lua script:
```
local state = redis.call('GET', 'driver_state:' .. driver_id)
if state == 'AVAILABLE' then
  redis.call('SET', 'driver_state:' .. driver_id, 'OFFERED', 'EX', '15')
  redis.call('ZREM', 'available_drivers:nyc', driver_id)
  return 1  -- success: we got this driver
else
  return 0  -- failed: driver already in another state
end
```
Lua scripts in Redis are atomic (single-threaded Redis executes them without interruption).
Only one Matching Service instance gets return value 1. The other gets 0 and tries the next candidate.

**Staff lesson:** Any state transition that must be exclusive (only one actor can "win") requires an atomic compare-and-swap. Redis Lua scripts, `SETNX`, or database `UPDATE WHERE state='expected'` are the tools. Never rely on "read then write" for exclusive state transitions in a distributed system.

---

### Incident 5: Uber Surge Pricing Loop (2015)

**Company:** Uber  
**What happened:** A bug in the surge pricing computation created a feedback loop. When surge prices were applied, driver supply increased (more drivers went online for higher earnings). The surge calculation read a higher supply number -> computed lower surge -> reduced the multiplier. Lower prices: riders returned, demand spiked. Next calculation window: low supply (drivers had gone offline after the surge reduced) -> surge activated again. The system oscillated between 3x surge and 1x every 5 minutes. Riders experienced extreme price volatility. Some riders submitted ride requests just before a surge window and paid 1x while neighboring riders paid 3x simultaneously.

**Root cause:** 5-minute recalculation window with no damping. The market signal (more drivers online) fed directly back into the surge calculation without smoothing.

**Fix:** Applied exponential moving average (EMA) to both supply and demand counts:
  `smoothed_supply = 0.7 * current_supply + 0.3 * previous_smoothed_supply`
Sudden supply spikes are dampened. Surge reduces gradually rather than instantly.
Added a minimum surge duration: once surge activates, it persists for at least 10 minutes (prevents oscillation at short time scales).

**Staff lesson:** Feedback systems oscillate when the response is too fast and too strong relative to the signal. Any control loop (surge pricing, autoscaling, rate limiting) needs damping and hysteresis: slow to react, slow to de-react. Pure proportional control oscillates; add derivative and integral terms (PID control) or simpler: smoothing + minimum duration.

---

## Exercises

### Exercise 1: GEOSEARCH Command

**Problem:** Write the Redis command to find the 10 nearest AVAILABLE drivers within 5km of coordinates (lat=40.7128, lng=-74.0060) in NYC, sorted by distance, returning their coordinates and distance in km.

**Solution:**

```
GEOSEARCH available_drivers:nyc FROMLONLAT -74.0060 40.7128 BYRADIUS 5 km ASC COUNT 10 WITHCOORD WITHDIST

Breaking down the command:
  available_drivers:nyc   -- the ZSET key (only available drivers in NYC)
  FROMLONLAT -74.0060 40.7128  -- center of search (longitude FIRST, then latitude)
  BYRADIUS 5 km           -- search by radius, 5km, in km units
  ASC                     -- sort nearest first
  COUNT 10                -- return at most 10 results
  WITHCOORD               -- include coordinates of each driver in response
  WITHDIST                -- include distance from search center

Example response:
  1) 1) "d_789"       <- driver_id
     2) "0.8124"      <- distance in km
     3) 1) "-74.0040" <- driver longitude
        2) "40.7135"  <- driver latitude

  2) 1) "d_456"
     2) "1.2389"
     3) 1) "-74.0065"
        2) "40.7218"
  
  ... (up to 10 results)

Note: GEORADIUS is deprecated since Redis 6.2. GEOSEARCH is the modern replacement.
In interviews: naming either is fine. Mention GEOSEARCH if asked about recent Redis.

What if fewer than 10 drivers are within 5km?
  GEOSEARCH returns however many are found (could be 0, 3, 7, etc.).
  Handling: if result count < 3 (too few options), expand to 10km:
  GEOSEARCH available_drivers:nyc FROMLONLAT -74.0060 40.7128 BYRADIUS 10 km ASC COUNT 10 WITHCOORD WITHDIST
```

---

### Exercise 2: Driver State Atomic Transition

**Problem:** Write the Redis Lua script to atomically transition a driver from AVAILABLE to OFFERED. The script should: check current state, set to OFFERED if AVAILABLE, remove from available_drivers ZSET. Return 1 on success, 0 if driver was not AVAILABLE.

**Solution:**

```
Lua script (called via EVAL command):

EVAL "
  local state = redis.call('GET', 'driver_state:' .. KEYS[1])
  if state == 'AVAILABLE' then
    redis.call('SET', 'driver_state:' .. KEYS[1], 'OFFERED', 'EX', ARGV[1])
    redis.call('ZREM', 'available_drivers:' .. KEYS[2], KEYS[1])
    return 1
  else
    return 0
  end
" 2 {driver_id} {city} {offer_timeout_seconds}

Example call:
  EVAL "..." 2 "d123" "nyc" "15"
  
  KEYS[1] = "d123"       (driver_id)
  KEYS[2] = "nyc"        (city)
  ARGV[1] = "15"         (offer timeout in seconds)

Why Lua script is atomic:
  Redis executes Lua scripts atomically — no other Redis commands run between
  the GET and the SET. This prevents two Matching Service instances from both
  reading 'AVAILABLE' and both winning the race.

Why pass driver_id and city as KEYS (not ARGV):
  Redis Cluster routes commands by key. If keys are passed as KEYS, Redis Cluster
  ensures all accessed keys are on the same shard (else throws CROSSSLOT error).
  Pass city and driver_id in KEYS if they might be on different shards.
  If using single Redis instance: no difference between KEYS and ARGV.

On success (return 1):
  Matching Service records: "I own driver d123 for trip t789"
  Sends push notification to driver.

On failure (return 0):
  Driver was already OFFERED (by another Matching Service instance) or EN_ROUTE.
  Matching Service: try next driver in ranked list.
```

---

### Exercise 3: Surge Pricing Math

**Problem:** In a hexagonal H3 cell covering downtown Manhattan: in the last 5 minutes, there were 450 ride requests and 120 available drivers. Using the surge tiers: ratio < 0.5 = 1.0x, 0.5-1.0 = 1.2x, 1.0-2.0 = 1.5x, 2.0-3.0 = 2.0x, > 3.0 = 2.5x. What is the surge multiplier? If a base fare is $8, what does the rider pay?

**Solution:**

```
Surge ratio = demand / supply
  demand = 450 ride requests per 5 minutes
  supply = 120 available drivers
  ratio = 450 / 120 = 3.75

Tier: ratio > 3.0 -> 2.5x surge multiplier

Rider fare:
  base_fare = $8.00
  surge_multiplier = 2.5
  rider_price = $8.00 * 2.5 = $20.00

Additional calculation — driver's share:
  If Uber takes 25% platform fee: driver earnings = $20.00 * 0.75 = $15.00
  Without surge: driver earnings = $8.00 * 0.75 = $6.00
  Surge increases driver earnings 2.5x -> incentive for drivers to go online.

Effect of surge on demand:
  Price elasticity for ride-sharing: ~0.5 (10% price increase -> 5% demand decrease)
  At 2.5x surge (150% price increase): expected demand decrease = 150% * 0.5 = 75%
  New demand = 450 * (1 - 0.75) = 112.5 requests
  New ratio = 112.5 / 120 = 0.94 -> falls to 1.2x surge tier
  
  This shows surge pricing is self-regulating:
  High surge -> riders leave -> demand drops -> surge decreases.
  In practice the response is not instant; there is a 5-minute calculation lag.
```

---

## Homework

**Short 1:** Open the Uber or Lyft app and watch the "driver dots" on the map. Count how often the nearest driver's dot moves. Is it exactly every 4 seconds? What happens when a driver is stopped at a red light? What does this tell you about how the location update frequency is configured in the real app?

**Short 2:** Experience surge pricing. During a busy weekend evening, open Uber and Lyft in the same area. Do they have different surge multipliers? What does this tell you about their surge calculation algorithms and market strategies?

**Short 3:** Read Uber's engineering blog post on H3 (Uber's Hexagonal Hierarchical Geospatial Indexing System). Why did Uber choose hexagons over squares for their geographic cells? What mathematical property of hexagons makes them better for distance calculations at cell boundaries?

**Deep:** Build a simplified location tracking and matching system:
- Simulate 1,000 "drivers" broadcasting random-walk GPS coordinates every 4 seconds into Redis GEOADD
- Implement a "match rider" function: given a rider's location, GEOSEARCH for the 10 nearest available drivers
- Add driver state machine: AVAILABLE -> OFFERED (SET NX with 10s expiry) -> AVAILABLE (on expiry or reject)
- Measure: how long does it take to find and offer a driver for 1 ride request? For 100 simultaneous ride requests?
- Bonus: add surge calculation — count simulated "requests" per geo-cell, compute multiplier

---

## Glossary

**GEOADD:** Redis command to add one or more geospatial members (longitude, latitude, name) to a sorted set. Internally encodes coordinates as a 52-bit GeoHash stored as the ZSET score.

**GEOSEARCH / GEORADIUS:** Redis command to find members within a radius of a point or bounding box. Returns members sorted by distance. O(N + log M) where N is the result count and M is the total members.

**GeoHash:** A hierarchical spatial encoding that maps 2D coordinates to a 1D string (or number) such that nearby points share common prefixes. Allows proximity search using a 1D sorted index.

**H3:** Uber's hexagonal hierarchical geospatial indexing system. Divides the Earth's surface into hexagonal cells at multiple resolutions. Used for surge pricing zones, supply/demand analysis, and route planning.

**Driver availability ZSET:** A Redis sorted set (`available_drivers:{city}`) containing only drivers whose state is AVAILABLE, stored with their GeoHash-encoded location. Matching service queries this ZSET to find candidates.

**Trip state machine:** The set of states a trip goes through from REQUESTED to COMPLETED. Each transition is published to Kafka for consumption by downstream services (notifications, pricing, analytics).

**Offer window:** The time given to a driver to respond to a trip offer (typically 10-15 seconds). If the driver does not respond, the offer expires and the next ranked driver receives the offer.

**Surge pricing:** A dynamic pricing mechanism that increases the fare multiplier when demand exceeds supply in a geographic area. Increases rider cost, increasing driver supply (higher earnings) and reducing rider demand until supply and demand balance.

**Thundering herd:** A failure pattern where many clients simultaneously attempt to reconnect to a recently recovered service, overloading it and causing it to crash again. Prevented by jittered exponential backoff.

**Compare-and-swap (CAS):** An atomic operation that reads a value, compares it to an expected value, and only writes the new value if the comparison succeeds. Used in Redis via Lua scripts or GETSET commands to prevent race conditions in state transitions.

---

## The One-Sentence Summary

> "Ride sharing = Redis GEOADD for real-time driver location (250K writes/sec, city-partitioned) + GEOSEARCH for nearest available driver matching (O(log N), sub-millisecond) + atomic compare-and-swap Lua script for AVAILABLE -> OFFERED state transition + Kafka event stream for trip state machine + WebSocket push for live location tracking — the hardest part is the location write throughput (solved by geo-partitioned Redis, one instance per city) and the driver offer race condition (solved by atomic Redis Lua compare-and-swap so only one matching service instance can claim a driver)."

---

## Interview Q&A — Most Common Cross-Questions

---

**Q1: Why use Redis for driver location instead of a regular database?**

At 1 million drivers pinging every 4 seconds, that is 250,000 writes per second. A typical PostgreSQL instance handles 10,000-30,000 writes per second. Even with PostGIS (geospatial extension), the location update table would need 8-25 instances just for writes. More critically, the geospatial search — finding drivers within 5km — is O(N) without specialized indexing and O(log N + results) with a GeoHash index. Redis GEOADD encodes each driver's position as a GeoHash ZSET score, making the write O(log N) and the search GEOSEARCH also O(log N + results), all in memory at sub-millisecond latency. For a real-time matching system where matching must complete in under 500ms, in-memory geospatial indexing is not a luxury — it is a requirement.

---

**Q2: How does Redis GEOADD work internally?**

Redis GEO is a sorted set (ZSET) with a special encoding. The longitude and latitude are encoded as a 52-bit GeoHash, a technique that interleaves the binary representations of the normalized latitude and longitude. The interleaving preserves proximity: two points that are geographically close produce similar GeoHash numbers, so they land near each other in the ZSET's sorted order. When you call GEOSEARCH for points within 5km, Redis finds the range of GeoHash values that covers the search area (the center cell and 8 surrounding cells in a 3x3 grid), does a ZSET range scan to retrieve candidates, and then filters by exact Haversine distance. This turns a 2D proximity search into a 1D sorted index scan — the same trick that makes GeoHash efficient everywhere.

---

**Q3: How do you prevent two matching service instances from offering the same driver to two riders simultaneously?**

The AVAILABLE to OFFERED state transition must be atomic. If two Matching Service instances both read the same driver as AVAILABLE and both try to offer them, a naive "read, then write" approach lets both win. The fix is a Redis Lua script that reads the driver's state and, only if it is AVAILABLE, atomically sets it to OFFERED and removes the driver from the available ZSET. Redis executes Lua scripts in a single-threaded fashion — no other commands run between the read and the write. The Lua script returns 1 if it succeeded in claiming the driver, or 0 if the driver was already in a different state. Only the Matching Service instance that gets a return value of 1 sends the offer. The other tries the next candidate.

---

**Q4: What is the trip state machine and why is it persisted to Kafka?**

The trip state machine has states: REQUESTED, MATCHED, DRIVER_EN_ROUTE, RIDER_PICKED_UP, COMPLETED, and CANCELLED. Every state transition is stored durably in Postgres (the authoritative record) and published as an event to Kafka. Kafka decouples the Trip Service from all consumers: the Notification Service reads MATCHED events to push "driver found" to the rider, the Pricing Service reads COMPLETED events to compute the fare, the Driver Earnings Service reads COMPLETED to credit the driver, and the Analytics Service reads everything for dashboards. Without Kafka, the Trip Service would need to directly call 4+ downstream services on every state change — coupling that causes failures to cascade. Kafka's durability (RF=3) also means events are not lost if a consumer is temporarily down.

---

**Q5: How does the rider see the driver's live location moving on the map?**

The driver app sends a GPS update every 4 seconds. The Location Service writes this to Redis (GEOADD) and publishes to Kafka. A Trip Tracking consumer reads from Kafka, checks whether the driver has an active trip (GET driver_active_trip:{driver_id} in Redis), and if so, pushes the driver's new coordinates to the rider's WebSocket connection. The Notification Service knows which WebSocket server node handles this rider's connection (stored as GET rider_ws:{rider_id} in Redis). The rider's app renders the updated position on the map. The update cycle is every 4 seconds — the driver's ping rate. The rider sees the driver's dot moving smoothly on the map as a result of these 4-second pushes.

---

**Q6: What is surge pricing and how is it calculated?**

Surge pricing raises the fare multiplier when demand exceeds supply in a geographic area. The city is divided into hexagonal cells (using Uber's H3 library). Every 5 minutes, the Pricing Service counts ride requests and available drivers per cell. The ratio (requests / drivers) determines the multiplier tier: below 0.5 is no surge, 0.5-1.0 is 1.2x, 1.0-2.0 is 1.5x, 2.0-3.0 is 2.0x, and above 3.0 is 2.5x (capped). The multiplier is stored in Redis with a 5-minute TTL. When a rider requests a ride, the Pricing Service reads the surge for their pickup cell and includes it in the price estimate. Surge is locked in at the time the rider confirms — they pay the price shown, even if conditions change during their wait.

---

**Q7: What happens if a city's Redis instance crashes during active trips?**

Active trips in progress (driver already matched and en route) are recorded in Postgres. The trip status (DRIVER_EN_ROUTE, RIDER_PICKED_UP) is durable. Losing Redis only affects: (1) live location updates — the rider's map stops updating for 30-60 seconds while Redis restarts, and (2) new match requests — GEOSEARCH fails until Redis repopulates. For live location: fall back to Cassandra for the last known driver location (latency goes from 1ms to 20ms). For new matches: either expand the search to a neighboring city's Redis or serve a "temporarily unavailable" response (graceful degradation). Drivers automatically re-populate the Redis ZSET within 30-60 seconds via their ongoing 4-second pings. No trip data is lost.

---

**Q8: How do you handle the situation where the driver app crashes mid-trip?**

The driver's TTL-gated Redis state handles offline drivers automatically. The driver's state entry (`SET driver_state:{driver_id} "EN_ROUTE" EX 30`) is refreshed every time a location ping arrives. If the driver's app crashes, pings stop. After 30 seconds of no pings, the TTL expires and the driver's state entry disappears from Redis. The Trip Service detects this via a Kafka heartbeat consumer: if no driver location events arrive for a trip's driver for 60 seconds, flag the trip as "driver unresponsive." The rider app shows a "we've lost contact with your driver" message. The Trip Service escalates: attempt to call the driver, wait 2 minutes, then cancel the trip with no cancellation fee to the rider and compensate the driver proportionally.

---

**Q9: How do you scale if a single city (like New York City) has more drivers than one Redis instance can handle?**

NYC at peak might have 80,000 drivers. At 70 bytes each: 5.6 MB — trivially fits in one Redis instance. The issue is not memory but write throughput: 80,000 drivers / 4 seconds = 20,000 GEOADD/sec. Redis handles 100,000-500,000 ops/sec. A single instance is at 4-20% capacity. Fine. But if a single city grew to 1 million drivers (unrealistic but hypothetical): 250,000 GEOADD/sec — near the single-instance ceiling. Solution: sub-city partitioning via consistent hashing on the driver's geohash prefix. Each partition covers a geographic quadrant. A GEOSEARCH spanning a boundary queries 2-4 partitions in parallel and merges results. This is a "fan-out read" — more expensive than a single query, but necessary for extreme scale.

---

**Q10: Why are hexagons (H3) better than squares (a grid) for surge pricing zones?**

In a square grid, a cell shares its edges with 4 neighbors and its corners with 4 more. The distance from the center of a square to the center of a corner-adjacent neighbor is √2 ≈ 1.41 times the distance to an edge-adjacent neighbor. This inconsistency means two adjacent cells can have significantly different proximity relationships. A rider in one cell may be much closer to the center of a diagonal neighbor than of an edge neighbor, but the grid treats all neighbors equally. In a hexagonal grid, every cell shares an edge with exactly 6 neighbors, and the distance from the center of any hexagon to the center of any of its 6 neighbors is exactly equal. This uniform distance property means that surge zone calculations at cell boundaries are consistent in all directions. It also means that a hexagonal cell more closely approximates a circle — the natural shape of a "nearby area" — than a square cell does.

---

*Section 5 — L5 / Senior SWE. Frequently asked at Uber, Lyft, DoorDash, Instacart, and any marketplace with real-time logistics. Pairs with Ch61f (Leaderboard for Redis ZSET concepts) and Ch60 (Real-Time Chat for WebSocket notification patterns).*

---

**Q11: How do you handle the driver going offline mid-trip (phone dies, app crashes)?**

The driver's location pings arrive every 4 seconds. Each ping refreshes a TTL-gated key: `SET driver_state:{driver_id} "EN_ROUTE" EX 30`. If the phone dies, pings stop. After 30 seconds, the TTL expires. A Trip Watchdog Service subscribes to TTL expiry events (Redis keyspace notifications) or polls every 15 seconds for trips whose driver last-ping is older than 45 seconds. Detection steps: (1) Log the driver as unresponsive. (2) Show the rider "We've lost contact with your driver" with an ETA confidence interval widened. (3) Attempt to call the driver via the platform. (4) After 2 minutes of no contact: initiate driver replacement. Find the next nearest available driver and offer them the trip with the current rider pickup location. (5) If no replacement available within 3 minutes: cancel the trip, notify rider, zero cancellation fee. Credit the rider $5 inconvenience credit. The driver who went offline is marked for review and their next 3 trips are monitored for repeat disconnects.

---

**Q12: How does ETA calculation work — how accurate is the estimated arrival time?**

ETA is computed by a Routing Service that takes driver location → rider pickup → destination and queries a road network graph. The road network is stored as a directed weighted graph where edge weights are dynamic (real-time travel time, not distance). The weights are updated every 5 minutes using: (1) historical speed data for that road segment at this time of day and day of week, (2) live traffic data from a third-party provider (Google Maps Platform or HERE), and (3) Uber's own telemetry — if 1,000 drivers on a road segment are going 10 mph instead of the usual 40 mph, that data updates the edge weight in real time. Dijkstra's algorithm (A* with geographic heuristic) computes the shortest-time path.

ETA accuracy degrades with distance. For the driver-to-pickup leg (typically < 5 minutes): p90 accuracy is ±1 minute. For the full trip duration (potentially 45 minutes): p90 accuracy is ±7 minutes. The longer the trip, the larger the compounding uncertainty from traffic changes that occur during the trip. Uber uses machine learning to calibrate ETA accuracy post-trip: for each historical trip, compare predicted ETA to actual time, learn the correction factor by route/time/traffic condition.

---

**Q13: How do you design the cancellation penalty system fairly?**

Cancellation policies: (1) rider cancels before driver accepts → no fee. (2) rider cancels after driver accepts but before driver departs → no fee if within 2 minutes, else $5 fee. (3) rider cancels after driver is en route → $5 fee. (4) driver cancels after accepting → driver rating docked, no fee to rider.

Implementation: on CANCEL event, the Trip Service checks state machine: was the trip in MATCHED state for more than 2 minutes? Was it in DRIVER_EN_ROUTE? Reads trip_accepted_at timestamp from the trips table, computes elapsed seconds, applies the policy. The cancellation fee is charged immediately (same payment method on file) via the Payment Service, same saga pattern as a normal trip fare.

Fairness edge cases: if the driver's ETA was misrepresented (driver showed 3 minutes but was actually 15 minutes away), the rider gets the fee waived if the cancellation was within 5 minutes of discovering the actual ETA. The Trip Service checks driver_actual_arrival_lat/lng at the time of cancellation vs driver_accepted_location — if driver was > 50% farther than the stated ETA, auto-waive the fee. This logic lives in a separate CancellationFeeDecision service, making it easy to update policy without touching the core Trip State Machine.

---

**Q14: How do you handle multi-stop trips (rider wants to pick up a friend en route)?**

A multi-stop trip has an ordered list of waypoints: pickup → stop_1 → stop_2 → destination. The data model: `trips.route = [{lat, lng, type: 'pickup'}, {lat, lng, type: 'stop'}, {lat, lng, type: 'dropoff'}]`. The Routing Service computes the full polyline across all waypoints. The fare is calculated as the sum of segments between waypoints.

State machine extension: add a BETWEEN_STOPS state after the first stop. The driver app shows the next waypoint. The rider confirms arrival at each stop (marks it as completed). The trip transitions through sub-states: PICKUP_COMPLETED → HEADING_TO_STOP_1 → STOP_1_COMPLETED → HEADING_TO_DROPOFF. If the rider cancels between stops, the fare calculation uses the distance actually traveled to that point.

For routing: the order of multi-stop waypoints can be optimized (Traveling Salesman Problem for 2-3 stops). Since N is very small (at most 3-4 stops), brute-force enumeration of all permutations (at most 24) is fast enough — no need for a complex TSP solver.

---

**Q15: How do you design driver earnings and payout — when and how do drivers get paid?**

Driver earnings are calculated on TRIP_COMPLETED. The fare breakdown: base fare + per-mile rate + per-minute rate + surge multiplier + tolls − Uber commission (20-25%). This is stored as an `earnings` record: `driver_id, trip_id, gross_fare, commission_rate, net_earnings, earned_at`.

Payout models: (1) Weekly payout: sum net_earnings for the week, transfer via ACH to bank account (2-3 business days). (2) Instant payout: driver can request same-day payout for $1.99 fee, settled via debit card push (Visa Direct, 30 minutes). (3) Earnings balance: drivers accumulate balance and cash out when desired.

The balance is maintained in a `driver_wallets` table: `driver_id, balance_cents, last_updated`. On TRIP_COMPLETED, the earnings service updates the balance: `UPDATE driver_wallets SET balance_cents = balance_cents + net_earnings WHERE driver_id=?`. This is idempotent only with the trip_id as an idempotency key: `INSERT INTO driver_earnings (trip_id, net_earnings) ON CONFLICT (trip_id) DO NOTHING` — if already processed, skip.

---

## Monitoring and Observability

### Key Metrics by Subsystem

**Driver location tracking:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `location_pings_per_sec` | 250K | Drop > 20% sustained (GPS outage, app crash) |
| `redis_geoadd_latency_p99_ms` | < 2ms | > 10ms (Redis under memory pressure) |
| `driver_ttl_expiry_rate_per_min` | < 100 | > 5,000 (mass driver disconnection or TTL too short) |
| `location_age_p99_sec` | < 8s | > 20s (pings arriving stale — network issue) |

**Driver matching:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `match_success_rate_%` | > 90% | < 70% (supply/demand imbalance or geosearch failure) |
| `match_latency_p99_ms` | < 500ms | > 2,000ms (Lua script contention or GEOSEARCH slow) |
| `double_offer_rate` | 0 | > 0 (Lua atomic transition failing — investigate Redis cluster) |
| `driver_acceptance_rate_%` | > 80% | < 60% (drivers rejecting offers — investigate incentives) |

**Trip state machine:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `trips_stuck_in_state_over_10min` | 0 | > 0 (state machine deadlock — manual investigation) |
| `saga_failure_rate_%` | < 1% | > 5% (payment/notification downstream failure) |
| `cancellation_rate_%` | 5–15% | > 25% (UX issue, ETA mismatch, or supply problem) |

**Surge pricing:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `surge_recalculation_latency_ms` | < 200ms | > 1,000ms (H3 cell aggregation too slow) |
| `surge_multiplier_p99` | < 3.0 | > 5.0 (extremely high surge — check for event or incident) |
| `surge_zone_boundary_cross_count` | low | Spike (drivers/riders repeatedly crossing surge boundary — feedback loop) |

### Distributed Trace: Match Request Flow

```
Trace: match_rider_to_driver (request_id)
  ├─ Span 1: api_gateway (POST /rides)                        3ms
  ├─ Span 2: geosearch (GEOSEARCH available_drivers:NYC)      1ms   ← location index here
  ├─ Span 3: driver_claim (Lua atomic AVAILABLE→OFFERED)      2ms   ← contention shows here
  ├─ Span 4: offer_push (WebSocket → driver app)             50ms
  ├─ Span 5: driver_accept (await accept event, max 15s)    3,000ms ← timeout common
  └─ Span 6: trip_create (INSERT trips + Kafka publish)       8ms
```

Alert on: Span 3 returning 0 (driver claimed by another instance) rate > 30% (high contention), Span 5 timeout rate > 20% (drivers slow to accept — add more in GEOSEARCH radius).

---

## Capacity Planning — NYC at Peak

**Scale:** NYC peak, 80,000 active drivers, 50,000 concurrent riders.

**Location updates:**
```
80,000 drivers × 1 ping/4 sec = 20,000 GEOADD/sec to Redis
Each GEOADD: O(log N) on N=80,000 entries → sub-millisecond
Redis: 20,000 ops/sec at 1 Gbps throughput → uses < 5% capacity
Driver GeoHash ZSET: 80,000 drivers × 70 bytes = 5.6 MB → fits in Redis without memory pressure
```

**Match requests:**
```
50,000 concurrent riders, avg trip request every 5 min
50,000 / 300 sec = 167 new ride requests/sec
Each match: 1 GEOSEARCH + 1 Lua script per attempt (avg 1.3 attempts before success)
GEOSEARCH: O(log N + results) for N=80K, results=10 → ~1ms
167 × 1.3 = 217 Lua executions/sec → trivial for Redis
```

**Kafka trip events:**
```
167 trips starting/sec × avg 15-min trip = 167 × 15 × 60 / 60 = 2,500 concurrent active trips
Each trip: 6 state transitions × 167 trips/sec = 1,000 Kafka events/sec
Kafka: 3 partitions per city, 1,000 events/sec → trivial
```

**WebSocket connections:**
```
50,000 riders + 80,000 drivers = 130,000 WebSocket connections
Each connection sends/receives ~10 messages/sec (location updates for active trips)
130,000 × 10 × 200 bytes = 260 MB/sec = 2 Gbps → need 3 WebSocket servers at 1 Gbps each
```

**Redis memory total (NYC city shard):**
```
Driver GeoHash ZSET:       5.6 MB
Driver state keys:         80,000 × 50 bytes = 4 MB
Surge multiplier cells:    ~10,000 H3 cells × 50 bytes = 500 KB
Active trip index:         2,500 trips × 200 bytes = 500 KB
Total:                     ~11 MB → fits in 512 MB Redis instance with 98% headroom
```

---

## Common Anti-Patterns

**Anti-pattern 1: Non-atomic driver state transition**
```python
# WRONG: read-check-write is a race condition
driver_state = redis.get(f"driver_state:{driver_id}")
if driver_state == "AVAILABLE":
    redis.set(f"driver_state:{driver_id}", "OFFERED")
# Two matching service instances both read AVAILABLE and both set OFFERED
# Driver gets offered to two riders simultaneously
```
Fix: Use a Redis Lua script that reads and conditionally writes atomically. Redis executes Lua scripts single-threaded — no other commands run between the read and write.

**Anti-pattern 2: Storing all drivers in one global GeoHash ZSET**
```
# WRONG: one ZSET for all 5 million global drivers
available_drivers:global  →  5M drivers × 70 bytes = 350 MB per ZSET
GEOSEARCH latency: O(log 5M + results) = slower than O(log 80K + results)
Write throughput: 5M drivers / 4 sec = 1.25M GEOADD/sec → saturates single Redis
```
Fix: Partition by city. `available_drivers:NYC`, `available_drivers:SFO`, etc. Each shard has 1K-100K drivers. GEOSEARCH is faster, writes are distributed. Cross-city requests are extremely rare (airport pickups near borders handled by geographic overlap).

**Anti-pattern 3: No driver TTL heartbeat**
```python
# WRONG: driver state set once with no expiry
redis.set(f"driver_state:{driver_id}", "AVAILABLE")  # no EX
# Driver app crashes → state stays AVAILABLE forever
# Rider gets matched to a phantom driver
```
Fix: Every location ping refreshes the TTL: `redis.set(f"driver_state:{driver_id}", "AVAILABLE", ex=30)`. If no ping in 30 seconds, the key expires and the driver disappears from the available pool automatically.

**Anti-pattern 4: Calculating surge with a fixed grid instead of H3**
```
# WRONG: fixed rectangular grid
grid = 0.01° × 0.01° tiles (~1 km × 1 km)
# Problem 1: tile borders are arbitrary lines that bisect neighborhoods
# Problem 2: tiles at different latitudes have different areas (0.01° longitude is shorter near poles)
# Problem 3: adjacent tile distance is not consistent (corner neighbors are 1.4× farther than edge neighbors)
```
Fix: H3 hexagonal grid. All adjacent cells have the same center-to-center distance. Hexagons better approximate circles (the natural shape of "nearby area"). H3 cell sizes are uniform in area (H3 level 9 cells are ~0.1 km²).

**Anti-pattern 5: Polling for driver location instead of push**
```javascript
// WRONG: rider app polls every second for driver location
setInterval(() => {
  fetch('/trips/T123/driver_location')  // 50,000 riders × 1 poll/sec = 50,000 req/sec!
}, 1000)
```
Fix: Driver location updates are pushed via WebSocket from the Trip Tracking Service. The rider app passively receives updates. Reduces "driver location" endpoint from 50,000 req/sec to near zero (only initial load and reconnects).

---

## Production Incident Deep Dives (Extended)

### Incident 6: Uber Sydney NYE Surge Price 8.0× — Algorithmic Feedback Loop (2015)

**What happened:** New Year's Eve in Sydney. An explosion occurred near a major entertainment district. People fled the area simultaneously and opened Uber simultaneously — the surge algorithm saw demand spike to 8× normal. Surge price jumped to 8.0×. This caused: (1) anger on social media, (2) many riders cancelled rides (too expensive), (3) fewer riders → lower demand count in next 5-minute surge window. But supply of drivers had also dropped (many left the surge zone due to crowd safety concerns). The next calculation: lower demand but even lower supply → surge stayed at 7.5×. The algorithm was stuck in a high-surge equilibrium driven by fear/avoidance of the surge zone itself.

**Root cause:** Surge algorithm only measured instantaneous demand/supply ratio, not latent demand (the people who wanted rides but were deterred by surge). A high surge price doesn't mean demand is being met — it can mean demand is being suppressed.

**Fixes:**
1. Manual surge override: ops team can cap surge at 4× during emergency/news events.
2. Demand sensitivity cap: if rider cancellation rate > 60% in a cell, don't increase surge further — high cancellations signal price elasticity limit reached.
3. EMA damping on surge increases (already present but coefficient too small — reduced spike height).
4. Safety event detection: if surge in a cell coincides with breaking news (Slack alert integration with news API), alert on-call to evaluate manual cap.

---

### Incident 7: Matching Service Thundering Herd at Airport Queue (2017)

**Date:** JFK Airport, Thanksgiving 2017. Approximately 300 Uber drivers were in the airport holding area. When flights began landing at 6 PM, 2,400 riders simultaneously opened the Uber app and requested rides.

**What happened:** All 2,400 match requests arrived in the same 30-second window. The Matching Service was stateless and horizontally scaled (40 instances). All 40 instances simultaneously called GEOSEARCH on the same `available_drivers:JFK` ZSET. GEOSEARCH is O(log N + results) and reads are non-blocking in Redis — this was not the bottleneck. The bottleneck was the Lua atomic script: each instance tried to atomically transition a driver from AVAILABLE→OFFERED. With 300 available drivers and 2,400 requests, the first 300 requests succeeded. The next 2,100 requests each tried all available drivers, got 0 from every Lua call (all drivers OFFERED), and returned "no drivers available" to the rider.

The riders immediately retried. 2,400 × retry attempts × 40 Matching Service instances = thundering herd on the GEOSEARCH Redis endpoint.

**Root cause:** No backoff or jitter on rider retry after "no drivers available." All retried in the same second.

**Fix:**
1. **Exponential backoff with full jitter on rider retry:** wait 2 + random(0, 4) seconds before retry. Spreads the retry storm.
2. **Waiting room for airport queue:** at airports (detected by geofence), queue rider requests instead of returning immediate "no drivers" — hold for up to 3 minutes while driver pool refreshes.
3. **Airport supply pre-warming:** 5 minutes before scheduled flight arrivals (pulled from airport API), increase the release rate from the driver holding area to pre-position supply.

---

## Additional Exercises

### Exercise 4: Surge Pricing Cell Design

**Problem:** Design the data schema and query for computing surge multiplier for all H3 cells in San Francisco (approximately 500 H3 level-9 cells covering the city). Every 5 minutes, count ride requests and available drivers per cell. Compute multiplier. Store and retrieve for the pricing calculation.

**Solution:**

```sql
-- H3 cell surge state in Redis
-- Key: surge:{city}:{h3_cell_id}
-- Value: multiplier float
-- TTL: 5 minutes + 30s buffer

-- Surge calculation every 5 min (cron):
-- Step 1: Count ride requests in last 5 min per H3 cell
SELECT 
    h3_cell_id,
    COUNT(*) as request_count
FROM trip_requests
WHERE requested_at > NOW() - INTERVAL '5 minutes'
  AND city_id = 'SFO'
GROUP BY h3_cell_id;

-- Step 2: Count available drivers per H3 cell (from Redis)
-- GEOSEARCH each cell's center with radius 200m:
for cell_id in sfo_cells:
    center = h3_to_lat_lng(cell_id)
    drivers = redis.geosearch("available_drivers:SFO",
                              fromlonlat=center,
                              byradius=200, unit='m')
    driver_count[cell_id] = len(drivers)

-- Step 3: Compute multiplier
for cell_id in sfo_cells:
    ratio = request_count.get(cell_id, 0) / max(driver_count.get(cell_id, 1), 1)
    if ratio < 0.5:    multiplier = 1.0
    elif ratio < 1.0:  multiplier = 1.2
    elif ratio < 2.0:  multiplier = 1.5
    elif ratio < 3.0:  multiplier = 2.0
    else:              multiplier = min(ratio * 0.8, 4.0)  # cap at 4×
    
    # EMA smoothing: blend with previous multiplier
    prev = float(redis.get(f"surge:SFO:{cell_id}") or 1.0)
    smoothed = 0.7 * multiplier + 0.3 * prev
    redis.set(f"surge:SFO:{cell_id}", round(smoothed, 1), ex=330)  # 5.5 min TTL

-- Step 4: Pricing read (< 1ms)
def get_fare_multiplier(pickup_lat, pickup_lng):
    cell_id = lat_lng_to_h3(pickup_lat, pickup_lng, resolution=9)
    multiplier = redis.get(f"surge:SFO:{cell_id}")
    return float(multiplier) if multiplier else 1.0
```

---

### Exercise 5: Designing the Driver Earnings Reconciliation

**Problem:** Drivers earn money on every trip. Their earnings must match the company's ledger exactly. Design a reconciliation process that detects and fixes discrepancies between the driver's balance in `driver_wallets` and the sum of their completed trip earnings.

**Solution:**

```python
# Nightly reconciliation job (runs at 2 AM, low-traffic period)

def reconcile_driver(driver_id):
    # Step 1: Sum earnings from source of truth (trip records)
    db_sum = db.query("""
        SELECT COALESCE(SUM(net_earnings_cents), 0)
        FROM driver_earnings
        WHERE driver_id = ?
          AND trip_completed_at >= current_payout_period_start
          AND payout_id IS NULL  -- not yet paid out
    """, [driver_id]).scalar()
    
    # Step 2: Read current wallet balance
    wallet_balance = db.query("""
        SELECT balance_cents FROM driver_wallets WHERE driver_id = ?
    """, [driver_id]).scalar()
    
    # Step 3: Compare
    if db_sum == wallet_balance:
        return  # All good
    
    discrepancy = db_sum - wallet_balance
    
    # Step 4: Log the discrepancy for audit
    db.insert("driver_reconciliation_errors", {
        "driver_id": driver_id,
        "expected": db_sum,
        "actual": wallet_balance,
        "discrepancy": discrepancy,
        "detected_at": NOW()
    })
    
    # Step 5: Auto-correct small discrepancies (< $0.10, likely floating point)
    if abs(discrepancy) < 10:  # cents
        db.update("driver_wallets", 
                  {"balance_cents": db_sum},
                  {"driver_id": driver_id})
        return
    
    # Step 6: Flag large discrepancies for manual review
    alert_ops(f"Driver {driver_id}: balance discrepancy of {discrepancy/100:.2f} USD")

# Idempotency guarantee: each trip's earnings are applied exactly once:
def apply_trip_earnings(trip_id, driver_id, net_earnings_cents):
    rows = db.execute("""
        INSERT INTO driver_earnings (trip_id, driver_id, net_earnings_cents)
        VALUES (?, ?, ?)
        ON CONFLICT (trip_id) DO NOTHING
    """, [trip_id, driver_id, net_earnings_cents])
    
    if rows.rowcount == 0:
        return  # Already applied
    
    # Update wallet balance
    db.execute("""
        UPDATE driver_wallets
        SET balance_cents = balance_cents + ?
        WHERE driver_id = ?
    """, [net_earnings_cents, driver_id])
```

---

## L5 vs L6 Calibration Table — Ride Sharing

| Topic | L5 Answer | L6/Staff Answer |
|-------|-----------|-----------------|
| Driver location storage | Redis GEOADD per city shard; GEOSEARCH for nearest K drivers | Plus: spatial sharding within large cities (quadrant keys); Cassandra as warm backup for last-known location; 52-bit GeoHash precision analysis (meters of error per bit) |
| Atomic driver assignment | Redis Lua script AVAILABLE→OFFERED; retry next candidate on failure | Plus: optimistic lock-free approaches (CAS retry budget); driver claim queue to serialize contention at extreme scale; secondary accept window (20s) for driver hesitation |
| Surge pricing | H3 cells; 5-min demand/supply ratio; EMA smoothing; cap at 4× | Plus: ML demand forecasting (predict demand 15 min ahead to pre-position supply); price elasticity model per market (different cap in regulated jurisdictions); multi-product surge (UberX vs Comfort in same cell) |
| Trip state machine | REQUESTED→MATCHED→EN_ROUTE→PICKED_UP→COMPLETED; Kafka per transition | Plus: Choreography (event-driven) vs Orchestration; compensation on partial trip completion (driver drops off early); multi-stop state extension (HEADING_TO_STOP, AT_STOP) |
| Driver TTL heartbeat | SET driver_state EX 30; GEOADD every ping | Plus: graceful offline transition (drain in-flight offers before TTL expiry); OFFLINE state vs expired-key distinction for analytics; adaptive TTL (shorter during city traffic anomaly detection) |
| Matching radius | 5km radius, expand to 10km if no drivers in 30s | Plus: demand density–aware radius (dense downtown: 2km, suburban: 10km); dynamic expansion rate based on wait-time target SLA; pre-positioning dispatch (suggest drivers move to demand hotspot) |
| ETA | Dijkstra/A* on live traffic graph; p90 ±1 min for < 5-min trips | Plus: ML-calibrated ETA with historical trip telemetry; real-time graph edge weight decay (use driver GPS telemetry to infer congestion 60s before third-party data reflects it) |
| Earnings | Net fare per trip; weekly ACH or Instant Pay via Visa Direct | Plus: incentive multiplier programs (streak bonuses, guarantee programs); driver tax document generation (1099-K at year end); real-time earnings visibility (not just balance, but in-progress trip forecast) |

---

## Additional Exercises

### Exercise 5: GeoSearch Boundary Precision Analysis

**Problem:** A driver is 4.98 km from a rider. Your GEOSEARCH radius is set to 5 km. Should the driver appear in the results? What about a driver at exactly 5.00 km? Analyze Redis's GeoHash precision at the 5 km radius.

**Solution:**

```
Redis GEOADD encodes lat/lng as a 52-bit GeoHash integer.
Precision analysis at 52 bits:
  - 26 bits for longitude → 2^26 = 67M positions across 360° = ~5.4 meters resolution
  - 26 bits for latitude → ~2.7 meters resolution
  
Redis GEOSEARCH precision:
  - GEOSEARCH uses 8 GeoHash cells around the search center to cover the radius
  - Cell boundaries are GeoHash cell borders — not perfect circles
  - The search area is a rounded rectangle, not a circle
  - Error at boundaries: up to ±0.6% of the radius at the outermost cells
  
At 5 km radius:
  - Precision error: ±0.6% × 5 km = ±30 meters
  - A driver at 4,970m → definitely inside (5,000 - 4,970 = 30m > max error) ✓
  - A driver at 4,985m → likely inside, but GeoHash rounding might exclude them
  - A driver at exactly 5,000m → ~50% chance of appearing (exactly at boundary)
  - A driver at 5,030m → might appear (boundary precision issue)
  
Redis documentation: "The command performs an approximate search with a small margin (≤ 0.6%)."

Real-world implication:
  A driver at 5,010m might appear in a 5km GEOSEARCH (false positive).
  A driver at 4,995m might not appear (false negative).
  
Fix: do not make business-critical decisions based on GEOSEARCH membership alone.
After GEOSEARCH returns candidates, compute the exact Haversine distance
for each candidate and filter:
  
  candidates = redis.geosearch("available_drivers:NYC", fromlonlat=(lng, lat),
                               byradius=5, unit='km', count=20)
  
  # Post-filter with exact distance
  precise_candidates = []
  for driver_id, driver_coords in candidates:
      exact_dist = haversine(rider_coords, driver_coords)  # exact in meters
      if exact_dist <= 5000:
          precise_candidates.append((driver_id, exact_dist))
  
  # Sort by exact distance
  precise_candidates.sort(key=lambda x: x[1])
  
This adds O(K) Haversine computations (K = number of GEOSEARCH results, typically 10-20).
At sub-microsecond per Haversine computation: negligible overhead.
```

---

### Exercise 6: Trip Fare Calculation Under Variable Surge

**Problem:** A rider requests a trip at 5:00 PM when surge is 2.0×. The trip takes 25 minutes. During the trip, surge in that area drops to 1.0× at 5:15 PM. What price does the rider pay?

**Solution:**

```
Policy: surge is locked in at trip START (when rider confirms the trip), not dynamically adjusted during the trip.

Reason: otherwise a rider who starts during high surge would face an unpredictable final fare.
The rider confirmed the price estimate at 5:00 PM with 2.0× surge — they should pay that.

Implementation:
  trips table: {
    trip_id, rider_id, driver_id,
    surge_multiplier_at_start: 2.0,  -- locked when rider confirms
    started_at: 17:00:00,
    ...
  }
  
Fare calculation (runs at TRIP_COMPLETED):
  base_fare = base_rate + (per_mile_rate × miles_driven) + (per_minute_rate × minutes)
  surge_fare = base_fare × surge_multiplier_at_start  -- always uses the locked 2.0×
  final_fare = surge_fare + tolls + airport_surcharge (if applicable)

What about price estimates shown to riders?
  The estimate at booking time uses: current_surge × estimated_distance × estimated_time
  Estimate: 2.0 × ($2.00 + $1.50/mi × 8 mi + $0.25/min × 25 min) = 2.0 × $20.25 = $40.50
  
  Actual fare may differ from estimate if: actual route differs (different distance),
  actual time differs (traffic), or tolls differ.
  
  Uber guarantees: final fare will be within 20% of the estimate for most trips.
  If actual > estimate × 1.2: Uber covers the overage (not charged to rider) for promotional reasons.
  
Surge lock timestamp:
  Store locked_at = time of rider confirmation (not driver match).
  If rider sees surge, confirms, then waits in queue for 15 min before being matched:
    locked_at = 5:00 PM, current_surge_at_match = 1.5×
    Rider still pays 2.0× (their confirmation time locked it)
    This is UberPool's "Guaranteed Price" feature — the estimate includes a surge at confirmation.
```

---

### Exercise 7: Geofencing for Airport Drop-Off Rules

**Problem:** New York JFK Airport has a special rule: drivers can only drop off in Terminal areas (defined polygons), not on the adjacent highway. Design a geofencing check that runs at trip completion to validate the driver's final location.

**Solution:**

```python
# Airport geofence defined as a set of polygons
# Each polygon is a list of (lat, lng) vertices
JFK_DROP_OFF_ZONES = [
    # Terminal 1
    [(40.6414, -73.7897), (40.6414, -73.7870), (40.6398, -73.7870), (40.6398, -73.7897)],
    # Terminal 2
    [(40.6425, -73.7900), (40.6425, -73.7880), (40.6410, -73.7880), (40.6410, -73.7900)],
    # ... more terminals
]

JFK_AIRPORT_BOUNDARY = [
    # Outer bounding box of the airport
    (40.6350, -73.8050), (40.6500, -73.8050),
    (40.6500, -73.7800), (40.6350, -73.7800)
]

def point_in_polygon(lat, lng, polygon):
    """Ray casting algorithm — O(N) where N = polygon vertices"""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lng) != (yj > lng)) and (lat < (xj - xi) * (lng - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def validate_dropoff(driver_final_lat, driver_final_lng):
    # Step 1: Are we even near JFK?
    if not point_in_polygon(driver_final_lat, driver_final_lng, JFK_AIRPORT_BOUNDARY):
        return {"valid": True, "reason": "Not in airport area"}  # Normal trip
    
    # Step 2: Are we in a valid drop-off zone?
    for zone in JFK_DROP_OFF_ZONES:
        if point_in_polygon(driver_final_lat, driver_final_lng, zone):
            return {"valid": True, "reason": "Valid terminal drop-off"}
    
    # Step 3: In airport but not in a drop-off zone
    return {
        "valid": False,
        "reason": "Drop-off location is not in a terminal area",
        "guidance": "Please proceed to the nearest terminal for drop-off"
    }

# Optimization: polygons are pre-loaded into Redis as GeoJSON at startup.
# Point-in-polygon is computed at trip end (not during the trip).
# For real-time guidance during the trip: check within 500m of airport boundary only.
```

---

## Key Interview Signals — What L5 Looks Like In the Room

**Signal 1: You partition driver location by city from the start.**
Many candidates design a single global `available_drivers` Redis ZSET. An L5 candidate immediately proposes city-level partitioning, citing write throughput (250K GEOADD/sec for 1M drivers globally vs 20K for NYC), and explains that cross-city trips are rare enough to handle as edge cases. This shows awareness of Redis single-instance throughput limits without being prompted.

**Signal 2: You explain the Lua script for atomic state transition.**
When asked "how do you prevent two matchers from offering the same driver?", weak candidates say "use a lock." L5 candidates describe the Redis Lua script: read driver state, check it's AVAILABLE, atomically write OFFERED, return success/failure. They explain that Lua scripts in Redis are single-threaded (no other commands execute during the script), making this a compare-and-swap without requiring a separate lock primitive.

**Signal 3: You bring up surge pricing feedback loops.**
The Sydney 2015 incident where surge suppressed demand (which then lowered surge, but supply was also low) is a classic second-order effect. An L5 candidate mentions that naive surge calculations based on instantaneous demand/supply can create oscillations, and that EMA smoothing and a manual override capability are engineering requirements, not optional features.

**Signal 4: You address the TTL heartbeat pattern for driver availability.**
Setting driver state with no TTL means crashed drivers permanently occupy the AVAILABLE pool. L5 candidates describe the TTL refresh pattern — `SET driver_state EX 30` refreshed on every location ping — and explain what happens when the TTL expires (driver automatically disappears from the pool). This demonstrates understanding of Redis TTL as a self-healing consistency mechanism, not just a cache expiry tool.

**Signal 5: You distinguish matching latency requirements from database throughput requirements.**
Location writes (250K/sec) require Redis (in-memory). Match decisions (167/sec) require Redis for consistency. Trip state (durable) requires Postgres. Driver earnings (financial accuracy) require Postgres. An L5 candidate naturally routes each concern to the right tier without being asked, and explains why each tier is appropriate for its concern.

---

## Related Topics to Review After This Chapter

- **Ch61f (Leaderboard — Redis ZSET):** Redis GEOADD stores driver locations as a scored ZSET (GeoHash as score). Understanding Redis ZSET internals from Ch61f explains why GEOSEARCH is O(log N + results) — it's a range scan on the sorted GeoHash ZSET, same data structure as leaderboard rank queries.
- **Ch60 (Real-Time Chat / WebSocket):** The driver-to-rider live location updates use WebSocket push from the Trip Tracking Service. This is the same fan-out architecture as real-time chat — one message (driver location) pushed to the subscribing rider's WebSocket connection. If you understand how to route a chat message to the right WebSocket server, you understand how to route a location update to the right WebSocket server.
- **Ch58 (Payment Flow):** Ride-sharing fare collection at trip end uses the same saga pattern as ticketing (trip completion → charge fare → update driver earnings). The payment service integration — idempotency key = trip_id, saga orchestration for retry on payment failure — is covered in Ch58.
- **H3 library documentation (external reading):** Uber's H3 hexagonal grid library is open-source (github.com/uber/h3). The resolution levels, area per cell, and the adjacency functions (k-ring for finding neighboring cells) are documented with examples. Understanding H3 resolution 9 cells (~0.1 km²) for surge pricing and H3 resolution 12 cells (~0.003 km²) for precise pickup routing makes your surge pricing discussion much more concrete in an interview.
- **Uber Engineering Blog (external reading):** Uber has published extensively about H3, surge pricing algorithms, and their matching architecture. Searching "Uber engineering blog H3" and "Uber engineering surge pricing" gives production-grade context that rounds out the academic treatment in this chapter.

---

## Quick Reference: Redis Commands Used in Ride Sharing

| Operation | Redis Command | Complexity | Notes |
|-----------|---------------|------------|-------|
| Add/update driver location | `GEOADD available_drivers:{city} lng lat driver_id` | O(log N) | N = active drivers in city |
| Find nearest drivers | `GEOSEARCH available_drivers:{city} FROMLONLAT lng lat BYRADIUS 5 km COUNT 10` | O(log N + K) | K = results returned |
| Atomic state transition | Lua script: GET + conditional SET | O(1) | Atomic compare-and-swap |
| Driver TTL heartbeat | `SET driver_state:{id} "AVAILABLE" EX 30` | O(1) | Auto-expires if no pings |
| Get surge for cell | `GET surge:{city}:{h3_cell_id}` | O(1) | Returns float multiplier |
| Active trip lookup | `GET driver_active_trip:{driver_id}` | O(1) | trip_id or nil |
| Rider's WebSocket server | `GET rider_ws:{rider_id}` | O(1) | Points to WS server node |

**GeoHash precision at 52 bits:** ~0.6mm horizontal resolution. Sufficient for street-level accuracy. GPS receiver error (5-10 meters) dominates over GeoHash precision error.

---

## Additional Exercise: Driver Incentive Program Design

### Exercise 8: Guaranteed Earnings and Streak Bonuses

**Problem:** Uber offers a guarantee: "Drive 30 trips this week and earn at least $800, or we'll pay the difference." Design the system to track progress toward the guarantee in real time and pay out at week end.

**Solution:**

```python
# Guarantee enrollment
CREATE TABLE driver_guarantees (
  guarantee_id     BIGSERIAL PRIMARY KEY,
  driver_id        BIGINT,
  week_start       DATE,           -- Monday 00:00 UTC
  week_end         DATE,           -- Sunday 23:59 UTC
  trips_required   INT,            -- 30
  earnings_floor   INT,            -- 80000 cents = $800
  trips_completed  INT DEFAULT 0,
  actual_earnings  INT DEFAULT 0,  -- cents
  status           VARCHAR(20) DEFAULT 'ACTIVE',  -- ACTIVE, QUALIFIED, PAID_OUT, EXPIRED
  enrolled_at      TIMESTAMP,
  paid_out_at      TIMESTAMP
);

# Real-time progress tracking (Redis for low-latency read)
# Updated on every TRIP_COMPLETED event

def on_trip_completed(driver_id, net_earnings_cents, week_start):
    guarantee_id = redis.get(f"active_guarantee:{driver_id}:{week_start}")
    if not guarantee_id:
        return  # Driver not enrolled this week
    
    # Increment counters atomically
    pipeline = redis.pipeline()
    pipeline.hincrby(f"guarantee_progress:{guarantee_id}", "trips", 1)
    pipeline.hincrby(f"guarantee_progress:{guarantee_id}", "earnings", net_earnings_cents)
    trips, earnings = pipeline.execute()
    
    # Persist to DB (for payout accuracy)
    db.execute("""
        UPDATE driver_guarantees
        SET trips_completed = trips_completed + 1,
            actual_earnings = actual_earnings + ?
        WHERE guarantee_id = ?
    """, [net_earnings_cents, guarantee_id])
    
    # Check if qualification threshold reached
    if trips >= 30 and earnings >= 80000:
        db.execute("""
            UPDATE driver_guarantees SET status = 'QUALIFIED'
            WHERE guarantee_id = ? AND status = 'ACTIVE'
        """, [guarantee_id])
        notify_driver(driver_id, "You've qualified for your guaranteed earnings!")

# Week-end payout job (runs Sunday 23:00 UTC)
def process_weekly_guarantees(week_start):
    qualified = db.query("""
        SELECT guarantee_id, driver_id, earnings_floor, actual_earnings
        FROM driver_guarantees
        WHERE week_start = ? AND status = 'QUALIFIED'
    """, [week_start])
    
    for g in qualified:
        payout_amount = max(0, g['earnings_floor'] - g['actual_earnings'])
        
        if payout_amount > 0:
            # Driver earned less than floor — pay the difference
            driver_payment_service.pay(
                driver_id=g['driver_id'],
                amount_cents=payout_amount,
                description=f"Weekly guarantee top-up: week of {week_start}",
                idempotency_key=f"guarantee_payout:{g['guarantee_id']}"
            )
        
        db.execute("""
            UPDATE driver_guarantees
            SET status = 'PAID_OUT', paid_out_at = NOW()
            WHERE guarantee_id = ?
        """, [g['guarantee_id']])

# Expired guarantees (driver didn't complete 30 trips)
def expire_unqualified_guarantees(week_start):
    db.execute("""
        UPDATE driver_guarantees
        SET status = 'EXPIRED'
        WHERE week_start = ? AND status = 'ACTIVE'
          AND trips_completed < trips_required
    """, [week_start])
    # No payout for expired guarantees

# Streak bonus: +$5 bonus for every 5 consecutive days with at least 3 trips
def check_streak_bonus(driver_id, date):
    consecutive_days = db.query("""
        SELECT COUNT(DISTINCT trip_date) as days
        FROM driver_trips
        WHERE driver_id = ?
          AND trip_date >= ? - INTERVAL '4 days'
          AND trip_date <= ?
        HAVING COUNT(*) FILTER (WHERE trip_date = ?) >= 3  -- today: >= 3 trips
    """, [driver_id, date, date, date]).scalar()
    
    if consecutive_days >= 5:
        pay_streak_bonus(driver_id, 500)  # $5.00 in cents
        log_bonus(driver_id, "streak_5_day", 500, date)
```

**Idempotency for bonus payouts:** each payout uses `idempotency_key=f"streak_bonus:{driver_id}:{date}"`. If the bonus job crashes and reruns, the payment provider returns the same result for the same key — no double payment. The same pattern applies to guarantee top-up payouts (`idempotency_key=f"guarantee_payout:{guarantee_id}"`).

**Analytics hook:** every bonus event (streak bonus, guarantee payout, incentive multiplier) is published to Kafka `driver_incentive_events`. The Data Warehouse team uses this to measure incentive program ROI: trips_per_driver increases by X% when a guarantee program is active in a city. This data drives the decision of which incentive programs to expand.

---

## Quick Reference: Trip State Machine Transitions

| From State | Event | To State | Action |
|------------|-------|----------|--------|
| — | Rider requests ride | REQUESTED | Insert trip record, publish to Kafka |
| REQUESTED | Driver matched | MATCHED | Update trip, notify rider + driver |
| MATCHED | Driver en route | DRIVER_EN_ROUTE | Start live location push to rider |
| DRIVER_EN_ROUTE | Driver arrives | DRIVER_ARRIVED | Push "driver arrived" notification |
| DRIVER_ARRIVED | Rider confirmed | RIDER_PICKED_UP | Start fare meter |
| RIDER_PICKED_UP | Trip ended by driver | COMPLETED | Calculate fare, charge rider, credit driver |
| Any state | Rider cancels | CANCELLED | Apply cancellation fee policy |
| REQUESTED or MATCHED | Driver cancels | CANCELLATION_DRIVER | Re-match or notify rider |
| DRIVER_EN_ROUTE | Driver unresponsive 2 min | UNRESPONSIVE | Attempt re-match |

**State persistence:** every state transition writes a row to `trip_events` table (`trip_id, from_state, to_state, occurred_at, actor_id`) in addition to updating the `trips.status` column. The `trips.status` is the current state (optimized for reads); the `trip_events` table is the full history (optimized for audit and replay). This event-sourcing pattern allows reconstructing any trip's history for customer support investigations.

**Idempotency on state transitions:** the Trip Service uses optimistic locking: `UPDATE trips SET status='MATCHED' WHERE trip_id=? AND status='REQUESTED'`. If the transition already happened (status is not REQUESTED), `rows_affected=0` and the call is treated as a no-op. This makes transition handlers idempotent — safe to retry on network failure. The Kafka consumer for trip events uses the same pattern: a duplicate DRIVER_ACCEPTED event results in a no-op UPDATE, not a double state change.

**Kafka partition key for trip events:** use `trip_id` as the Kafka partition key for `trip_state_transitions`. This ensures all events for a given trip land on the same partition and are consumed in order by the downstream services (Notification Service, Pricing Service, Analytics). Partitioning by `driver_id` or `rider_id` would be wrong — a driver may have multiple concurrent trips, and ordering guarantees are needed at the trip level, not the driver level. With 100,000 partitions and trip_ids distributed uniformly: average partition load = (167 trips/sec) / 100,000 partitions = 0.00167 trips/sec/partition — extremely low, guaranteeing in-order delivery with no partition hot spots.

In practice, Uber uses far fewer Kafka partitions (typically 64-256 per topic) because the ordering guarantee only needs to hold per-trip, and 64 partitions × 3 replicas × 1,000 events/sec = well within Kafka's per-partition throughput (Kafka comfortably handles 100,000 messages/sec per partition). The specific number of partitions is determined by the desired consumer parallelism (one consumer thread per partition maximum), not by event rate. For 50 Notification Service replicas each consuming 2 partitions: 100 partitions is sufficient and keeps operational complexity low.

**Kafka retention for trip events:** set retention to 7 days (not the default 168 hours — same number but making it explicit). This allows: replaying the last 7 days of events to rebuild downstream state (e.g., if the Pricing Service loses its derived aggregations), auditing disputed trips within the standard SLA window, and debugging production incidents that were noticed 2 days after they occurred. Retention beyond 7 days goes to a cold tier (S3 via Kafka Connect + Parquet format) for long-term analytics. The hot-tier cost: 1,000 events/sec × 7 days × 200 bytes/event = ~121 GB per Kafka cluster — trivial storage cost relative to the operational value of replay capability. Kafka compaction is not used for trip events (compaction retains only the latest message per key; trip events are append-only and need the full history, not just the latest state). Use log-retention (time-based), not log-compaction, for event sourcing topics.

**Consumer group isolation:** the Notification Service, Pricing Service, and Analytics Service each have their own Kafka consumer group for the `trip_state_transitions` topic. Each consumer group maintains its own offset — when the Notification Service restarts, it resumes from where it left off without affecting the Pricing Service's consumption. Consumer groups are the Kafka mechanism that enables one-to-many fan-out: one topic, N independent consumers, each seeing every message at their own pace. This is why Kafka (not Redis Pub/Sub) is used for trip events: Redis Pub/Sub has no persistence (messages lost if a consumer is offline), while Kafka's consumer group offset enables reliable at-least-once delivery to all consumers even through consumer restarts.

**Consumer lag as a health signal:** monitor consumer group lag (latest produced offset minus committed offset) per consumer group. Lag > 10,000 messages sustained for 60 seconds on the Notification consumer group means drivers are not receiving MATCHED events promptly, directly increasing cancellation rates. Scaling response: add consumer instances up to the partition count (one consumer per partition maximum); beyond that, add partitions first.
