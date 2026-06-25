# Chapter 74 — Location-Based Service (L5)

> L5 depth: nearby search (GeoHash), real-time object tracking (Redis GEO),
> combined read/write design, single-region. Skip: turn-by-turn navigation,
> multi-region geo-routing, ML ranking. Staff version = Ch101.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║  AT A GLANCE — LOCATION-BASED SERVICE (L5)                          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  WHAT:   Find nearby places (Yelp) + track moving objects (drivers) ║
║  SCALE:  500M places, 10M DAU, 1M concurrent driver updates/min     ║
║  LAT:    Place search < 100ms p99, driver lookup < 50ms p99         ║
║                                                                      ║
║  TWO SUBSYSTEMS                                                      ║
║  1. Place Search: static data, read-heavy, GeoHash index            ║
║     Write: place added/updated (infrequent)                         ║
║     Read: "find restaurants within 5km" — millions/day              ║
║                                                                      ║
║  2. Driver Location Tracking: dynamic data, write-heavy             ║
║     Write: each driver updates GPS every 4 seconds — 1M drivers     ║
║     Read: "find available drivers within 2km" — on every ride req   ║
║                                                                      ║
║  KEY INSIGHT:                                                        ║
║  Place search and driver search use the same spatial algorithm       ║
║  (GeoHash) but have opposite read/write ratios and different TTLs.  ║
║  The architecture is the same shape; the storage tier differs.      ║
║                                                                      ║
║  SECTIONS IN THIS CHAPTER                                           ║
║  1. The Problem    8. Hybrid read path                              ║
║  2. Requirements   9. Scaling                                       ║
║  3. HLD           10. Edge cases + failure modes                    ║
║  4. API Design    11. Interview application                         ║
║  5. DB Schema     12. Pre-interview drill                           ║
║  6. GeoHash deep  13. Capacity estimation                           ║
║  7. Redis GEO     14. Monitoring                                    ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Part 1: The Problem

### 1.1 What a Location-Based Service Does

Two problems that look different on the surface but share the same algorithmic core:

**Problem A — Static nearby search (Yelp-style)**
"Show me restaurants within 2 km of lat 37.78, lng -122.41, sorted by rating."
- Data: ~500M places globally (lat, lng, category, name, rating)
- Data changes rarely (a restaurant moves once a decade at most)
- Reads: millions per day; writes: thousands per day
- Challenge: how do you find all rows with lat/lng within a circular radius?

**Problem B — Real-time object tracking (Uber-style)**
"Find all available drivers within 3 km of lat 37.78, lng -122.41."
- Data: 1M active drivers, each updating location every 4 seconds
- Data changes constantly — every 4 seconds × 1M drivers = 250K writes/second
- Reads: every ride request queries nearby drivers — millions/day
- Challenge: same radius query as above, but data expires in seconds

Both problems fail in exactly the same way if you try the naive approach.

### 1.2 Why the Naive SQL Approach Fails

```sql
-- Naive: full table scan of 500M rows
SELECT * FROM places
WHERE category = 'restaurant'
  AND lat BETWEEN 37.74 AND 37.82
  AND lng BETWEEN -122.46 AND -122.37
ORDER BY rating DESC
LIMIT 20;
```

Even with a compound index on `(lat, lng)`, this query scans a rectangular bounding box
but cannot efficiently filter a circle. Worse, B-tree indexes are built for one dimension.
A `(lat, lng)` index is efficient on `lat` but still scans many rows with the right lat
and wrong lng. At 500M rows, this is a 10-100ms query that becomes 1,000ms under load.

For driver tracking: 250K writes/second to update `(driver_id, lat, lng)` in PostgreSQL
would saturate the write throughput of a standard primary + replica setup.

The solution to both: **spatial indexing**. Convert 2D coordinates to a 1D key that
preserves spatial locality, then use a standard key-value lookup.

---

## Part 2: Requirements

### 2.1 Functional Requirements

**Place search (Yelp subsystem):**
- Search for places by category within a radius (e.g., "pizza restaurants within 5 km")
- Return results sorted by distance or rating
- Support adding / updating / deleting places (admin-only)
- Return a place's details (name, address, lat/lng, category, rating, photo URLs)

**Driver tracking (ride-sharing subsystem):**
- Driver sends GPS update every 4 seconds
- Rider queries "find available drivers near me" (returns driver IDs + locations)
- Driver goes offline → location data should expire (TTL 30 seconds)
- Driver accepts ride → status changes from "available" to "on_trip"

### 2.2 Non-Functional Requirements

| Requirement | Target |
|---|---|
| Place search latency | p99 < 100ms |
| Driver location update | p99 < 50ms write |
| Driver search latency | p99 < 50ms read |
| Place data freshness | Eventual (minutes) |
| Driver data freshness | Real-time (4-second window) |
| Availability | 99.9% |
| Scale | 500M places, 1M concurrent drivers, 10M DAU riders |

### 2.3 Out of Scope (State Explicitly in Interview)

- Turn-by-turn navigation (routing graph traversal — see Ch101)
- Traffic-aware routing (real-time traffic ingestion)
- Multi-region geo-routing
- Place rating / review system (separate service)
- ML ranking of results (distance + rating heuristic is sufficient for L5)

---

## Part 3: High-Level Design

### 3.1 System Components

```
                    ┌──────────────────────────────────────────────────┐
                    │  LOCATION-BASED SERVICE — HIGH-LEVEL DESIGN       │
                    └──────────────────────────────────────────────────┘

┌──────────┐   Place Search   ┌───────────────┐   ┌─────────────────────────┐
│          │ ─────────────▶   │  Place Search  │──▶│  PostgreSQL + GeoHash   │
│  Client  │                  │  Service       │   │  (places table)          │
│ (Rider/  │                  └───────────────┘   └─────────────────────────┘
│  Driver  │
│  App)    │                  ┌───────────────┐   ┌─────────────────────────┐
│          │ ─────────────▶   │  Driver        │──▶│  Redis Cluster           │
│          │  Driver loc      │  Location      │   │  (GEOADD/GEORADIUS)      │
│          │  update          │  Service       │   │  Driver locations TTL    │
└──────────┘                  └───────────────┘   └─────────────────────────┘
                                      │
                                      ▼
                             ┌───────────────┐
                             │  Kafka         │
                             │  (location     │
                             │  update log)   │
                             └───────┬───────┘
                                     │
                             ┌───────▼───────┐
                             │  Location      │
                             │  History       │
                             │  Consumer      │
                             │  (writes to    │
                             │  PostgreSQL    │
                             │  for audit)    │
                             └───────────────┘
```

### 3.2 Write Paths

**Place write path (infrequent):**
```
Admin → POST /places → Place Service → PostgreSQL (places table, GeoHash computed and stored)
```

**Driver location update (high-frequency):**
```
Driver App → PUT /drivers/{id}/location → Driver Location Service
                                        → GEOADD drivers:available {lng} {lat} {driver_id}
                                        → SET driver:ttl:{driver_id} 1 EX 30
                                        → Kafka (location_updates topic) [async]
                                        → Response: 200 OK
```

### 3.3 Read Paths

**Place search:**
```
Client → GET /search/nearby?lat=X&lng=Y&radius=Z&category=C
       → Place Search Service:
           1. Encode (lat, lng) to GeoHash at correct precision
           2. Compute 8 neighbor cells
           3. SELECT * FROM places WHERE geohash_N = ANY([9 cells]) AND category = C
           4. Haversine-filter candidates to exact circle
           5. Sort by rating DESC, return top 20
```

**Driver search:**
```
Client → GET /drivers/nearby?lat=X&lng=Y&radius=Z
       → Driver Location Service:
           1. GEORADIUS drivers:available {lng} {lat} {radius} km ASC COUNT 10
           2. Return driver IDs + distances
```

---

## Part 4: API Design

### 4.1 Place Search API

```
GET /api/v1/places/search
Query parameters:
  lat      float   required  Viewer's latitude
  lng      float   required  Viewer's longitude
  radius   int     optional  Radius in meters (default 5000, max 50000)
  category string  optional  Place category filter
  limit    int     optional  Max results (default 20, max 100)
  cursor   string  optional  Pagination cursor

Response 200 OK:
{
  "places": [
    {
      "place_id": "p_abc123",
      "name": "Joe's Diner",
      "category": "restaurant",
      "lat": 37.781,
      "lng": -122.412,
      "distance_meters": 340,
      "rating": 4.5,
      "rating_count": 1203,
      "thumbnail_url": "https://cdn.example.com/places/p_abc123/thumb.jpg"
    }
  ],
  "total": 48,
  "next_cursor": "eyJ0eXBlIjoiZ2VvaGFzaCIsInByZWZpeCI6IjlxOGYiLCJvZmZzZXQiOjIwfQ"
}

GET /api/v1/places/{place_id}
Response 200 OK: { full place details including address, phone, hours, photos }

POST /api/v1/places   (admin only)
{ "name": ..., "category": ..., "lat": ..., "lng": ..., "address": ... }
Response 201 Created: { "place_id": "p_newxyz" }

DELETE /api/v1/places/{place_id}   (admin only — soft delete)
Response 204 No Content
```

### 4.2 Driver Location API

```
PUT /api/v1/drivers/{driver_id}/location    (driver app calls every 4 seconds)
{
  "lat": 37.782,
  "lng": -122.414,
  "heading": 90,        // degrees (0 = North)
  "speed_kph": 35,
  "status": "available" // available | on_trip | offline
}
Response 200 OK: {}

GET /api/v1/drivers/nearby
Query parameters:
  lat    float  required  Center latitude
  lng    float  required  Center longitude
  radius int    optional  Radius in meters (default 2000, max 10000)
  limit  int    optional  Max results (default 10)

Response 200 OK:
{
  "drivers": [
    {
      "driver_id": "d_456",
      "lat": 37.780,
      "lng": -122.413,
      "distance_meters": 120,
      "heading": 45,
      "vehicle_type": "sedan"
    }
  ]
}
```

---

## Part 5: Database Schema

### 5.1 Places Table (PostgreSQL)

```sql
CREATE TABLE places (
  place_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT         NOT NULL,
  category      TEXT         NOT NULL,
  address       TEXT         NOT NULL,
  lat           DOUBLE PRECISION NOT NULL,
  lng           DOUBLE PRECISION NOT NULL,
  geohash_6     CHAR(6)      NOT NULL,   -- precision 6: ~1.2km × 0.6km cell
  geohash_5     CHAR(5)      NOT NULL,   -- precision 5: ~4.9km × 4.9km cell
  phone         TEXT,
  website       TEXT,
  rating        NUMERIC(3,2) DEFAULT 0,
  rating_count  INT          DEFAULT 0,
  is_deleted    BOOLEAN      DEFAULT FALSE,
  created_at    TIMESTAMPTZ  DEFAULT now(),
  updated_at    TIMESTAMPTZ  DEFAULT now()
);

-- Primary spatial lookup: geohash cell + category filter
CREATE INDEX idx_places_geohash6_category
  ON places (geohash_6, category)
  WHERE is_deleted = FALSE;

CREATE INDEX idx_places_geohash5_category
  ON places (geohash_5, category)
  WHERE is_deleted = FALSE;
```

**Why store both `geohash_6` and `geohash_5`?** Different query radii need different
precision. For 1 km searches, precision 6 cells (~1.2 km × 0.6 km) tightly bound the
search. For 20 km searches, querying hundreds of precision-6 cells is slow — use
precision-5 cells instead (~4.9 km × 4.9 km). Having both precomputed avoids recomputing
the GeoHash at query time.

```sql
CREATE TABLE place_photos (
  photo_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id    UUID        REFERENCES places(place_id) ON DELETE CASCADE,
  url         TEXT        NOT NULL,
  is_primary  BOOLEAN     DEFAULT FALSE,
  uploaded_at TIMESTAMPTZ DEFAULT now()
);
```

### 5.2 Driver Location (Redis — Not PostgreSQL)

Driver locations are NOT stored in PostgreSQL during active tracking. The write rate
(250K writes/second for 1M drivers updating every 4 seconds) would saturate PostgreSQL.

```
Redis GEO ZSET:
  Key:     drivers:available
  Members: driver_id strings
  Score:   52-bit geospatial encoding of (lng, lat) — managed by Redis GEO commands

TTL per driver (per-member TTL is not natively supported in Redis ZSET):
  Key:  driver:ttl:{driver_id}
  Type: String, value = 1
  TTL:  30 seconds (EX 30)
  
  On expiry (keyspace notification):
    Handler: ZREM drivers:available {driver_id}

Driver metadata (heading, vehicle type) in a separate Redis Hash:
  Key:  driver:meta:{driver_id}
  Type: Hash
  Fields: heading, speed_kph, vehicle_type
  TTL: 60 seconds (refreshed on each location update)
```

### 5.3 Driver Location History (PostgreSQL — async write via Kafka)

```sql
CREATE TABLE driver_location_history (
  id          BIGSERIAL    PRIMARY KEY,
  driver_id   UUID         NOT NULL,
  lat         DOUBLE PRECISION NOT NULL,
  lng         DOUBLE PRECISION NOT NULL,
  heading     SMALLINT,
  speed_kph   SMALLINT,
  recorded_at TIMESTAMPTZ  DEFAULT now()
) PARTITION BY RANGE (recorded_at);  -- monthly partitions

CREATE INDEX idx_driver_loc_history_driver_ts
  ON driver_location_history (driver_id, recorded_at DESC);
```

Used for: trip route replay, driver behavior analytics, dispute resolution. Written
asynchronously by a Kafka consumer — NOT in the request path.

---

## Part 6: GeoHash Deep Dive

### 6.1 What GeoHash Is

GeoHash converts a (lat, lng) pair into a compact string where strings that share a prefix
are geographically nearby. The longer the shared prefix, the closer the locations.

```
GeoHash encoding overview for (lat=37.781, lng=-122.412):
  1. Interleave binary representations of normalized lat and lng
  2. Group into 5-bit chunks
  3. Map each chunk to Base32 alphabet (0-9, b-z excluding 'a', 'i', 'l', 'o')
  Result: "9q8yy" (precision 5) or "9q8yy9" (precision 6)

GeoHash precision table:
  Precision  Cell size (lat × lng)        Use case
  5          ~4.9 km × 4.9 km             5 km radius search
  6          ~1.2 km × 0.6 km             1 km radius search
  7          ~152 m × 152 m               0.2 km radius search
  8          ~38 m × 19 m                 walking-distance precision

Key property: two places with the same GeoHash-5 prefix are within 4.9 km of each other.
Two places with GeoHash-6 match are within 1.2 km. This is the index lookup key.
```

### 6.2 The 9-Cell Neighbor Query

A user near the boundary of a GeoHash cell might be close to a place in an adjacent cell.
Solution: always query center cell + 8 neighbors = 9 cells total.

```python
def nearby_places(lat: float, lng: float, radius_m: int, category: str) -> list:
    precision = 6 if radius_m <= 1000 else 5  # choose cell size
    center_hash = geohash_encode(lat, lng, precision=precision)
    neighbor_hashes = geohash_neighbors(center_hash)    # 8 neighbors
    cells = [center_hash] + list(neighbor_hashes)       # 9 total

    candidates = db.query(
        """SELECT * FROM places
           WHERE geohash_{p} = ANY(%s)
             AND category = %s
             AND is_deleted = FALSE""".format(p=precision),
        params=(cells, category)
    )

    # Exact circle filter (fast, in-memory)
    results = [
        p for p in candidates
        if haversine_distance(lat, lng, p.lat, p.lng) <= radius_m
    ]
    results.sort(key=lambda p: (-p.rating, haversine_distance(lat, lng, p.lat, p.lng)))
    return results[:20]
```

The 9-cell query returns a rectangular bounding box of candidates. Haversine filtering
trims this to the exact circle. The extra candidates (corners of the bounding box outside
the circle) are discarded in-memory in microseconds — not a performance concern.

### 6.3 Precision Selection Logic

```
SEARCH RADIUS    GEOHASH PRECISION   CELL SIZE          # CELLS QUERIED
≤ 300m           7                   152m × 152m        9
≤ 1km            6                   1.2km × 0.6km      9
≤ 5km            5                   4.9km × 4.9km      9
5km–20km         4 + 5               39km × 20km        Expand to more cells
> 20km           Cap search radius + show "expand search" message
```

For radii above 5 km, the 9-cell query at precision 5 already covers ~15 km × 15 km.
For radii above 20 km, the candidate count explodes — hundreds of cells, millions of rows.
Practical solution: cap the search radius at 50 km for L5. Beyond 50 km, the use case is
different (trip planning, not "nearby") and requires a different algorithm.

### 6.4 GeoHash vs PostGIS (Know Both for Interviews)

GeoHash (described above): index on a precomputed string column. Simple to implement
without database extensions. Works in any relational DB.

PostGIS (PostgreSQL extension): adds a native `GEOMETRY` type with a GiST spatial index
(R-tree based). The query looks like:

```sql
SELECT * FROM places
WHERE ST_DWithin(
  ST_MakePoint(lng, lat)::geography,  -- place location
  ST_MakePoint(-122.41, 37.78)::geography,  -- search center
  2000  -- radius in meters
)
AND category = 'restaurant'
ORDER BY ST_Distance(location, query_point), rating DESC
LIMIT 20;
```

PostGIS is more accurate (no boundary problem, true circle query) and scales better for
very large datasets. In an interview, mention PostGIS as the production-grade choice, but
explain GeoHash when asked to explain the algorithm — it's simpler to walk through.

---

## Part 7: Redis GEO Commands Deep Dive

### 7.1 How Redis GEO Works Internally

Redis GEO commands are built on top of the ZSET data structure. Internally, Redis encodes
each (lng, lat) pair as a 52-bit geospatial hash and stores it as the ZSET score.
Members are the identifiers (driver IDs).

This means:
- `GEOADD` = `ZADD` with a geospatial-encoded score
- `GEORADIUS` = `ZRANGEBYSCORE` on a range covering the target area, then Haversine filter

Because it's a ZSET underneath:
- O(log N) insert
- O(N+log M) radius query (N = candidates in bounding box, M = total members)
- At most one entry per member — GEOADD for an existing driver_id updates their position

### 7.2 Driver TTL: The Keyspace Notification Pattern

Redis ZSET has no per-member TTL. To expire individual drivers:

```
On location update:
  GEOADD drivers:available {lng} {lat} {driver_id}
  SET    driver:ttl:{driver_id} 1 EX 30

On TTL expiry — Redis publishes to __keyevent@0__:expired channel:
  Event: "driver:ttl:d_456"
  Handler subscribes to this channel and executes:
    ZREM drivers:available d_456

Simpler alternative (scheduled job):
  Every 10 seconds: scan all driver:ttl:* keys. Any missing key (expired) 
  means the driver is offline → ZREM that driver from drivers:available.
  Tradeoff: up to 10-second lag; simpler to operate (no event listener).
```

### 7.3 GEORADIUS Query Example

```
Redis command:
  GEORADIUS drivers:available -122.414 37.782 2 km
    ASC          sort by distance, nearest first
    COUNT 10     return at most 10 results
    WITHCOORD    include coordinates
    WITHDIST     include distances in km

Response:
  1) 1) "d_456"
     2) "0.1203"         (distance in km)
     3) 1) "-122.4133"
        2) "37.7818"
  2) 1) "d_789"
     2) "0.8742"
     3) 1) "-122.4212"
        2) "37.7825"

Time complexity: O(N + log M)
  N = drivers in bounding box around the 2km radius (~20-200 in a typical city)
  M = total drivers in the ZSET (~1M at peak)
  In practice: < 5ms for 1M-member ZSET with a 2km radius query.

Note: GEORADIUS is deprecated in Redis 6.2; use GEOSEARCH instead:
  GEOSEARCH drivers:available FROMMEMBER user_loc BYRADIUS 2 km ASC COUNT 10
```

---

## Part 8: The Combined System — Hybrid Read Path

A real location-based service serves both place search and driver search from the same
app. The two queries are independent and run in parallel at the client (or BFF):

```
Rider opens app:
  Parallel requests:
  ├── GET /drivers/nearby?lat=X&lng=Y&radius=2km  →  Redis GEORADIUS  (~10ms)
  └── GET /places/search?lat=X&lng=Y&radius=2km&category=pickup_point
                                                 →  PostgreSQL GeoHash (~20ms)

Both resolve independently. Client merges and renders map:
  - Driver pins (live locations from Redis)
  - Place markers (pickup points from PostgreSQL)
```

The two storage tiers (Redis + PostgreSQL) are separate concerns. Keeping them separate
is the right architectural decision — you could replace one without touching the other.
Trying to build a single "geo-query" that spans both would be an anti-pattern.

---

## Part 9: Scaling

### 9.1 Place Search Scaling

```
READS:
  10M DAU × 10 searches/day = 100M queries/day = 1,160 QPS average
  Peak (5× avg): ~5,800 QPS
  
  PostgreSQL read replica capacity: 5,000-10,000 indexed queries/second
  → 2 read replicas for peak coverage; 3 for HA
  
WRITES:
  New places: ~1,000/day (infrequent, admin-only)
  Ratings updates: ~100K/day (background batch, not latency-sensitive)
  → Single primary handles writes with ease

CACHE (optional at L5):
  Popular cells (e.g., "restaurants near Union Square") → Redis cache
  Key: {geohash_6}:{category}. TTL: 60 seconds.
  Only add this cache if read replica shows > 80% utilization.
```

### 9.2 Driver Location Scaling

```
WRITE RATE: 1M drivers × (1 update / 4 seconds) = 250,000 GEOADD/second
  Single Redis instance: ~200,000 ops/sec → NOT sufficient

SOLUTION: Redis Cluster sharded by geographic region
  drivers:available:us-west, drivers:available:us-east, etc.
  Each region's cluster handles its own GEOADD writes and GEORADIUS reads.
  
  Single-region sizing (L5 scope):
    Redis Cluster: 6 primary nodes
    Each node: ~42,000 GEOADD/sec (250K / 6) → within 200K node capacity
    With write pipelining: headroom comfortable

  Shard key for single region: geohash prefix of driver location.
    e.g., all drivers with geohash starting "9q" → shard A
    GEORADIUS on shard A returns all matches in that geographic region.
```

### 9.3 Hot Cell Problem

Many drivers in one small area (e.g., taxis at JFK Airport, drivers near a big event):

For places: precision-6 GeoHash returns many candidates. Haversine filter reduces to 20.
Not a scaling problem — a few extra rows is fine.

For drivers: 500 drivers in a 1km radius = 500 members in the GEORADIUS result set.
Redis handles 500-member results in < 5ms. Write rate for one cell: 500 × 0.25 = 125
writes/second. Negligible.

Hot cells become a problem only at extreme scale (10K+ drivers in one cell) — an L6
concern. At L5, acknowledge it: "We'd monitor ZSET member density per geographic area
and add cell-level sharding if any single area exceeds 10K drivers."

---

## Part 10: Edge Cases and Failure Modes

### 10.1 Driver Location Goes Stale

**Scenario**: Driver app crashes. Driver is in Redis as "available" with a stale location.

**Mitigation**: The 30-second TTL on `driver:ttl:{driver_id}` removes the driver within
30 seconds. Ride dispatch confirms the driver is reachable before confirming a match.
If the driver doesn't ACK within 5 seconds: re-query, dispatch to the next driver.

### 10.2 Redis Driver ZSET Node Fails

**Scenario**: One Redis Cluster node fails. Its keyslots are served by the replica.
Promotion takes 10-30 seconds. Driver writes to those keyslots fail during promotion.

**Mitigation**:
1. Redis Sentinel / Cluster handles automatic failover (< 10 seconds typically).
2. During failover: driver location service queues writes in memory (30-second buffer).
3. After recovery: flush buffered writes. Drivers see no visible disruption.

If full cluster is lost (not just one node): ride dispatch shows "searching for drivers"
with a spinner; ride requests queue. When Redis recovers (typically < 60 seconds for
cloud managed Redis), drain the queue.

### 10.3 GeoHash Computation Bug (Lat/Lng Swap)

A common bug: passing arguments as `geohash_encode(lng, lat)` instead of `(lat, lng)`.
The stored GeoHash doesn't match the actual location — searches return wrong results.

**Mitigation**: Write a validation job that recomputes GeoHash for a random 1% sample of
places and compares with stored values. Alert on any discrepancy > 0.01%.

### 10.4 Search Radius Too Large

A user requests a 100 km radius search. The 9-cell query at precision 4 (39 km × 20 km
cells) would return many millions of candidates. Haversine filtering would be slow.

**Mitigation**: Cap the maximum radius at the API level (e.g., 50 km). Return a 400 error
for larger radii. At > 50 km, suggest a different UX: "Showing results near [city center]."

---

## Part 11: Interview Application

### 11.1 The 45-Minute Framework

```
MINUTE 0-5:   Clarify which system we're building.
              "Are we designing static place search (Yelp), driver tracking (Uber),
               or both?" This scoping question signals maturity.
              For L5: design one or both, but stay single-region.

MINUTE 5-10:  Requirements: 2 functional + 2 non-functional.
              Out of scope: routing, multi-region, ML ranking.

MINUTE 10-20: HLD — draw the two subsystems:
              Box 1: Place Search → PostgreSQL with GeoHash index.
              Box 2: Driver Location Service → Redis GEO Cluster.
              Box 3: Kafka (driver location log → history DB).
              Justify split: "static data in PostgreSQL, dynamic data in Redis."

MINUTE 20-30: GeoHash deep-dive:
              "Encode (lat, lng) to string. Nearby points share prefix. Query
               center cell + 8 neighbors. Haversine filter to exact circle."
              Draw the 3×3 grid. Explain precision choice.

MINUTE 30-38: Redis GEO:
              GEOADD / GEORADIUS / GEOSEARCH commands.
              Per-driver TTL pattern (separate key + keyspace notifications).
              Write rate math: 250K GEOADD/sec → Redis Cluster.

MINUTE 38-43: Failure modes + edge cases (stale driver, hot cell, lat/lng swap).

MINUTE 43-45: Monitoring + wrap-up. Summarize the two subsystems and justify each.
```

### 11.2 Questions to Answer Without Hesitation

**"Why not just query lat/lng with a B-tree index?"**

A B-tree index on `(lat, lng)` is efficient on `lat` but must scan all rows with the
matching lat range for every value of lng. For 500M rows, this is O(millions of rows).
GeoHash converts the 2D problem to a 1D string prefix lookup — O(log N) with tens to
hundreds of candidates. That's a 10,000× improvement in candidate set size.

**"Why Redis for driver locations instead of a time-series DB or PostgreSQL?"**

A time-series DB is optimized for time-range queries ("all locations in the last 5
minutes"), not spatial queries ("all locations within 2 km right now"). PostgreSQL can't
sustain 250K writes/second without extreme horizontal sharding. Redis GEO handles
250K GEOADD/second in a Redis Cluster and provides GEORADIUS for spatial search in < 5ms.

**"How do you handle a driver near the edge of their GeoHash cell disappearing from
the results?"**

This is the boundary problem. The fix is to always query all 9 cells (center + 8 neighbors).
This guarantees coverage of any search radius smaller than the cell size. Post-filter
with Haversine to return only what's inside the circle.

**"How does Redis GEORADIUS work internally?"**

GEORADIUS is built on ZSET. Internally, Redis encodes (lng, lat) as a 52-bit geohash
integer score. GEORADIUS translates the radius into a bounding box of hash values,
queries the ZSET for scores in that range (ZRANGEBYSCORE), then applies a Haversine
filter to trim the bounding box to a circle. O(N + log M) where N is candidates in
the bounding box and M is total members.

---

## Part 12: Pre-Interview Drill

### 12.1 Four Concepts to Explain Cold (Under 60 Seconds Each)

**Concept 1 — GeoHash 9-cell query:**
"GeoHash encodes lat/lng to a string; nearby points share a prefix. For a radius search,
I encode the query center, find the 9 cells covering the area (center + 8 neighbors),
query the DB for all places in those cells, then Haversine-filter to the exact circle."

**Concept 2 — Redis GEOADD/GEORADIUS:**
"GEOADD adds a location to a ZSET by encoding the coordinates as a 52-bit integer score.
GEORADIUS translates a search radius to a bounding box of integer scores, queries the
ZSET, then Haversine-filters to a circle. For 1M drivers in a Redis Cluster, a 2km
GEORADIUS takes < 5ms."

**Concept 3 — Per-driver TTL:**
"Redis ZSET has no per-member TTL. I use a separate key `driver:ttl:{id}` with EX 30.
When the driver sends a location update, I reset the TTL. When 30 seconds pass without
an update, the key expires, a keyspace notification fires, and I ZREM the driver from
the available ZSET."

**Concept 4 — The two-tier storage split:**
"Places are static and need rated search — PostgreSQL with a GeoHash indexed column.
Driver locations change every 4 seconds — 250K writes/second. That write rate exceeds
PostgreSQL capacity. Redis GEO handles 200K+ writes/second per node and provides
spatial queries natively. The two workloads have different characteristics; they need
different storage."

### 12.2 Three Diagrams to Draw Cold

**Diagram 1 — The 3×3 GeoHash grid:**
```
┌────┬────┬────┐
│ NW │ N  │ NE │
├────┼────┼────┤
│ W  │ ★  │ E  │  ★ = center cell (user's location)
├────┼────┼────┤
│ SW │ S  │ SE │
└────┴────┴────┘
Query: SELECT * FROM places WHERE geohash_6 = ANY([9 cells]) AND category = ?
Then: Haversine-filter to return only places inside the circle
```

**Diagram 2 — Driver location write path:**
```
Driver App → PUT /location
           → Driver Service
           ├── GEOADD drivers:available lng lat driver_id   [Redis]
           ├── SET driver:ttl:{id} 1 EX 30                  [Redis]
           └── Kafka: location_update event                  [async]
                        ↓
                  History Consumer → PostgreSQL driver_location_history
```

**Diagram 3 — Parallel place + driver query:**
```
Rider App opens map
  ├── GET /drivers/nearby → Redis GEORADIUS → [driver list]   10ms
  └── GET /places/search  → PostgreSQL GeoHash → [place list] 20ms
  Both resolve → Client merges → renders map with both layers
```

### 12.3 Interview Self-Check

- [ ] Can explain GeoHash precision table (precision 5 = 4.9km × 4.9km)?
- [ ] Knows the 9-cell query + Haversine filter pattern?
- [ ] Knows GEOADD and GEORADIUS (or GEOSEARCH) commands?
- [ ] Can calculate driver write rate: 1M × 0.25 = 250K writes/sec?
- [ ] Can justify Redis over PostgreSQL for drivers (250K writes/sec)?
- [ ] Knows the per-driver TTL pattern (separate key + keyspace notification)?
- [ ] Can state out of scope: routing, multi-region, ML ranking?
- [ ] Can name the two storage tiers and justify the split in one sentence?

---

## Part 13: Capacity Estimation Deep Dive

### 13.1 Place Search Sizing

```
PLACE SEARCH CAPACITY
======================

READS:
  10M DAU × 10 searches/day = 100M searches/day
  100M / 86,400 = 1,160 QPS average
  Peak (5× avg): 5,800 QPS

  PostgreSQL read replica: 5,000–10,000 indexed queries/sec
  → 1 read replica for average; 2 for peak; 3 for HA

WRITES:
  New places: ~1,000/day
  Rating updates (batch): ~100,000/day
  Both are trivially handled by a single primary

STORAGE:
  500M places × 200 bytes (row) = 100 GB raw data
  Two GeoHash indexes: 100 GB × 3 = 300 GB total (data + indexes)
  Photos (CDN): separate — not stored in PostgreSQL
  3× replication (1 primary + 2 replicas): 900 GB total

QUERY PERFORMANCE:
  Index scan on geohash_6 + category: returns ~100 candidates per cell
  9 cells × 100 candidates = 900 rows max
  In-memory Haversine filter on 900 rows: < 1ms
  Network + serialization: ~5ms
  Total: < 10ms server-side; < 30ms with network to client ✓
```

### 13.2 Driver Location Sizing

```
DRIVER LOCATION CAPACITY
=========================

WRITES:
  1M drivers × (1 update / 4 seconds) = 250,000 GEOADD/second
  
  Redis Cluster sizing:
    Single node capacity: 200,000 ops/sec (with pipelining: higher)
    For 250,000 writes/sec: minimum 2 nodes (125K each)
    With 50% headroom: 4 primary nodes + 4 replicas (8 nodes total)

READS:
  10M DAU × 2 queries/session (open app + request ride) = 20M/day
  Average: 231 GEORADIUS/sec. Peak (5×): 1,155 GEORADIUS/sec
  Single Redis node handles 100K GEORADIUS/sec → reads are not the bottleneck

MEMORY:
  1M drivers × (ZSET entry: 24 bytes + driver:ttl key: 64 bytes)
  = 1M × 88 bytes = 88 MB total Redis memory for driver data
  Trivial — Redis Cluster has GBs of RAM per node; memory is not the constraint

KAFKA (location update log):
  250,000 events/sec × 200 bytes = 50 MB/sec throughput
  Retain 7 days: 7 × 86,400 × 50 MB = 30 TB
  Kafka configuration: 8 partitions, 3 brokers with replication factor 3
```

### 13.3 History Storage Sizing

```
DRIVER LOCATION HISTORY (PostgreSQL)
======================================

Write rate after batching: 250K events/sec → batch consumer groups into 1K rows/batch
  Batch inserts: 250 batches/sec × 1,000 rows = 250K rows/sec
  PostgreSQL COPY performance: 100K–200K rows/sec per node
  → 2 PostgreSQL nodes for history writes (not in request path)

Storage growth:
  250K updates/sec × 100 bytes/row = 25 MB/sec
  Per day: 25 MB × 86,400 = 2.16 TB/day
  Per week: 15 TB

Lifecycle:
  Hot (< 7 days): SSD PostgreSQL: 15 TB
  Warm (7-90 days): object storage (S3): 90 × 2.16 TB = 194 TB → ~$4,500/month
  Archive (> 90 days): Glacier: low-cost, accessed only for legal disputes
```

---

## Part 14: Monitoring and Alerts

### 14.1 Key Metrics

```
PLACE SEARCH:
  p99 API latency: target < 100ms; alert at > 200ms
  PostgreSQL GeoHash query time p99: target < 20ms; alert at > 50ms
  Read replica replication lag: alert if > 1 second
  
DRIVER LOCATION:
  GEOADD latency p99: target < 5ms; alert at > 15ms
  GEORADIUS latency p99: target < 10ms; alert at > 30ms
  Redis memory per node: alert at > 80% utilization
  Active driver count: alert on sudden 50% drop (mass crash event)
  Stale driver rate: % of matched drivers who don't respond → target < 0.5%
  
KAFKA (driver update log):
  Consumer lag: alert if > 100,000 messages (history consumer is behind)
  Throughput: alert if < 200K events/sec for > 60 seconds
```

### 14.2 The Most Critical Alert: Driver Redis Unavailability

If the driver Redis Cluster goes down, ride dispatch is blind. This is a P0 incident.

Runbook:
1. `redis-cli cluster info` → check slot coverage and node states
2. If one node failed: auto-promoted replica should cover it in < 10 seconds
3. If full cluster down: fall back to degraded mode — show "searching for drivers" in the
   app, queue ride requests, retry for 60 seconds
4. If > 60 seconds: page on-call SRE; escalate to Redis Cluster full rebuild

---

## Part 15: L5 vs L6 Calibration Table

```
DIMENSION        L5 EXPECTATION                  L6 EXPECTATION
────────────────────────────────────────────────────────────────────────
Spatial index    GeoHash 9-cell + Haversine       GeoHash + knows PostGIS
                                                  R-tree (GiST); compares
                                                  accuracy and performance

Driver storage   Redis GEOADD/GEORADIUS           Redis GEO + explains 52-bit
                                                  ZSET encoding; knows
                                                  S2 geometry (Google alt)

Write scaling    "Redis Cluster"                  Geo-partitioned sharding;
                                                  consistent hashing ring;
                                                  hot-spot monitoring and
                                                  dynamic rebalancing

TTL handling     "EX 30 on driver key"           Keyspace notification arch;
                                                  thundering herd on mass
                                                  expiry (shift end = 100K
                                                  drivers go offline at once)

Failure modes    Redis down → show error          Degraded mode design; SLO
                                                  impact quantification; 
                                                  circuit breaker pattern

Multi-region     Not required at L5               Active-active vs active-passive
                                                  for geographic regions; 
                                                  geo-routing at DNS/LB level

Capacity         Rough: "250K writes/sec,         Detailed: separate write vs
                 need Redis Cluster"              read sizing; history storage
                                                  lifecycle; TCO analysis
────────────────────────────────────────────────────────────────────────
```

---

## Part 16: Intern → Staff Answer Progression

This table shows how the answer to "Design a location-based service" evolves with seniority.
If you find yourself giving an intern-level answer in a Senior interview, that's a signal to
practice. Read your answer against the L5 column before the interview.

```
QUESTION: "Find restaurants near me."

INTERN ANSWER:
  "I'd store all restaurants in a database with lat and lng columns,
   then query: SELECT * FROM restaurants WHERE lat BETWEEN X AND Y
   AND lng BETWEEN A AND B."
  Problems:
  - Correct direction but doesn't scale to 500M rows
  - Bounding box query, not circle — misses the geometry
  - No mention of indexing
  - Would return with pagination but doesn't know how to handle it correctly

JUNIOR ANSWER:
  "I'd add an index on (lat, lng) to make the query faster."
  Problems:
  - Doesn't know that a B-tree index on 2 columns is still O(millions of rows)
  - The compound index helps but not as much as they think
  - Still no spatial awareness

MID-LEVEL ANSWER:
  "I'd use a spatial index like PostGIS to do a circle query."
  Strengths:
  - Correct tool — PostGIS is the right answer for production
  Problems:
  - Can't explain HOW PostGIS works (GiST R-tree internals)
  - Doesn't consider the write-heavy driver tracking problem
  - Can't size the system

SENIOR (L5) ANSWER:
  "Two systems: GeoHash-indexed PostgreSQL for static place search,
   Redis GEO (GEORADIUS) for dynamic driver tracking. GeoHash encodes
   (lat, lng) to a prefix string; I query center + 8 neighbor cells,
   then Haversine-filter. Drivers write 250K GEOADD/second — Redis
   Cluster with 4 nodes handles this. Per-driver 30s TTL via separate
   key + keyspace notifications."
  ✓ This is the target answer for an L5 interview.

STAFF (L6) ANSWER:
  Same as L5, plus:
  - Mentions S2 geometry as a production alternative to GeoHash (what
    Google Maps actually uses)
  - Discusses multi-region active-active design for global driver tracking
  - Quantifies the thundering herd problem: 1M drivers ending shifts at
    5pm → 1M concurrent TTL expirations → 1M ZREM events in a 1-minute
    window → keyspace notification handler must be rate-limited
  - Proposes ETA-aware dispatch (don't dispatch the closest driver;
    dispatch the driver who arrives first given current traffic)
  - Discusses consistency: what if a driver's last known location in
    Redis is 30 seconds stale? How does dispatch handle uncertainty?
```

---

## Part 17: Common Interview Mistakes

These are the mistakes most candidates make on this problem. Know them so you don't repeat them.

**Mistake 1: Only designing place search, forgetting driver tracking.**
The most common failure. When the interviewer says "location-based service," many candidates
default to Yelp (static places). Always ask: "Is this static places, real-time objects, or
both?" and design both if given latitude. Driver tracking is where the interesting scaling
problem lives.

**Mistake 2: Proposing a PostGIS B-tree index instead of GeoHash.**
PostGIS is great, but if you can't explain how it works internally (GiST R-tree), it sounds
like name-dropping. Either explain it or use GeoHash (which you CAN explain from first
principles). Interviewers test understanding, not tool familiarity.

**Mistake 3: Suggesting PostgreSQL for driver location writes.**
"I'd have drivers update their lat/lng in the DB" — this fails at the math. 250K writes/sec
is the scale of a major e-commerce write path; PostgreSQL can't sustain this on a standard
setup. Always move high-frequency location writes to Redis.

**Mistake 4: Not addressing the TTL problem.**
Many candidates say "drivers update their location every 4 seconds" but don't think about
what happens when they stop. A driver who crashes or loses connectivity should not remain
as "available" for hours. The 30-second TTL mechanism is a critical design detail.

**Mistake 5: Querying only the center GeoHash cell.**
Without querying the 8 neighbors, a user at the edge of a cell misses results in adjacent
cells. This is a correctness bug, not just a performance issue. Always query 9 cells.

**Mistake 6: Conflating distance and routing.**
"Sort by distance" vs "sort by ETA (estimated time of arrival)" are different problems.
Distance is simple Haversine. ETA requires routing through a road graph. For L5: sort by
distance. Mention that a production system would use ETA but it's out of scope.

---

## Part 18: Brainstorming Q&A

**Q: A user reports that a restaurant 800m away doesn't appear in their "1km search."
What went wrong?**

Three possible root causes:
1. **GeoHash boundary**: the user and the restaurant are in different GeoHash cells and you
   didn't include neighbor cells. Fix: always query all 9 cells.
2. **Precision mismatch**: the place was stored with `geohash_5` (precision 5, ~4.9km cell)
   but the query used `geohash_6` (precision 6, ~1.2km cell). The restaurant's `geohash_6`
   value doesn't match the query cells. Fix: ensure the DB column and the query code use
   the same precision for the same radius range.
3. **Soft-deleted record**: `is_deleted = TRUE` — someone marked the place as deleted.
   Check the record directly: `SELECT * FROM places WHERE place_id = 'p_xyz'`. If deleted,
   verify whether the deletion was intentional.

**Q: How do you handle a user searching from an airplane (lat 35.6, lng -82.5,
altitude 10,000m)? GeoHash doesn't encode altitude.**

GeoHash encodes only (lat, lng) — it's a 2D projection onto the Earth's surface.
Altitude is ignored. For a "find nearby" query from an aircraft:
- The query returns places near the ground position directly below the aircraft.
- This is almost certainly not what the user wants (they want places near their destination).
- The fix is an app-level concern: if the device reports altitude > 500m, show a message
  "No results — you appear to be airborne. Searching near [destination]?" rather than
  returning a confusing list of inaccessible restaurants 10,000m below.

**Q: How do you implement "sort by popularity, not distance"?**

Add a `popularity_score` column to the `places` table (precomputed from view count,
rating, and booking volume). After the GeoHash 9-cell query and Haversine filter:

```python
candidates = haversine_filter(geohash_query(lat, lng, radius, category))
if sort_by == "popularity":
    candidates.sort(key=lambda p: -p.popularity_score)
elif sort_by == "distance":
    candidates.sort(key=lambda p: haversine_distance(lat, lng, p.lat, p.lng))
return candidates[:20]
```

The GeoHash query retrieves candidates efficiently. Sorting happens in-memory after
filtering. Since the candidate count is bounded (~100-900 rows), in-memory sort is fast.

**Q: How do you support a "search along a route" feature (find gas stations within
5km of my driving route)?**

This is an L6 concern, but worth knowing at L5 to say "out of scope":
The route is a polyline (sequence of lat/lng points). For each route segment, you'd generate
a set of GeoHash cells covering a 5km corridor around the segment. Then query all places
in those cells and filter by proximity to the polyline (not just the center point).
This is O(route_length × 9 cells per segment) cells to query — potentially thousands of
cells for a 100km route. Production systems use spatial join operators (PostGIS `ST_DWithin`
on a LINESTRING) rather than brute-force GeoHash expansion. State this as out of scope
for L5 and mention it would use PostGIS for the production implementation.

**Q: How would you add real-time occupancy information to places (e.g., "busy right now")?**

Separate from the location data model entirely. "Busy" data comes from a popularity
aggregation service that counts check-ins, orders, or foot-traffic signals per place per
time window. Store aggregated "current busyness" in a Redis Hash: `busy:{place_id}` with
TTL 5 minutes (refreshed every 5 minutes by the aggregation service). At search time:
for each result place, do a Redis HGET for the busyness score. Merge with search results
before returning. This is a parallel Redis lookup — adds < 1ms to the response time.

**Q: What if two drivers are at the exact same location (e.g., both waiting at the same
parking lot at the airport)?**

Redis GEO stores one entry per member (driver_id). Two drivers at the same location are
two separate ZSET members with the same (or nearly the same) geospatial score. GEORADIUS
returns both as separate results with distance ~0km. No conflict. The dispatch system
chooses one based on other criteria (rating, vehicle type, wait time in queue).

**Q: How do you search places by a name prefix (not location)?**

This is autocomplete, not spatial search — a different problem. For "find restaurants
starting with 'Joe'" you'd use a text search index (PostgreSQL `pg_trgm` extension for
trigram similarity, or a dedicated full-text search service like Elasticsearch). The
location filter would be applied AFTER the text search: find all places matching "Joe",
then filter to those within the radius. Or vice versa: find nearby places, then apply
text filter. The order depends on selectivity — if the radius filter is more selective,
do it first.

---

## Part 22: Interview One-Liners Cheat Sheet

Memorize these before the interview. Each is a one-sentence answer to a hard question,
followed by a one-sentence justification.

```
TOPIC → ONE-LINER + WHY
=========================

WHY NOT B-TREE INDEX ON (LAT, LNG)
"A B-tree index on (lat, lng) is efficient on lat but must scan all matching lat rows
 for every value of lng — O(millions of rows) for 500M places."
Why: B-trees are 1D; spatial data is 2D. GeoHash converts 2D to 1D prefix lookup.

THE CORE GEOHASH INSIGHT
"Strings sharing a prefix are geographically nearby — longer shared prefix = closer."
Why: GeoHash interleaves binary representations of lat and lng, so prefix bits encode
regional containment (like a quadrant tree).

9-CELL QUERY PURPOSE
"I query the center cell + 8 neighbors to cover the full search radius including the
 boundary — then Haversine-filter to discard corners outside the circle."
Why: A user at the edge of a cell is close to places in adjacent cells. Without neighbors,
you miss results up to cell_width × 2 away.

REDIS GEO OVER POSTGRESQL FOR DRIVERS
"250K GEOADD/sec exceeds PostgreSQL's write capacity. Redis handles 200K ops/sec per node
 and provides GEORADIUS natively — the right tool for spatial + high write frequency."

PER-DRIVER TTL APPROACH
"I use a separate key driver:ttl:{id} with EX 30. On expiry, a keyspace notification
 triggers ZREM from the available ZSET — because Redis ZSET has no per-member TTL."

PRECISION CHOICE RULE OF THUMB
"Precision 6 for ≤ 1km radius (cells 1.2km × 0.6km), precision 5 for ≤ 5km radius
 (cells 4.9km × 4.9km). Cell size should be smaller than the search radius."
Why: If cells are larger than the radius, the 9 cells you query are too coarse and
return too many false positives.

GEORADIUS TIME COMPLEXITY
"O(N + log M) where N is candidates in the bounding box and M is total members.
 For 1M drivers and a 2km radius: ~50-200 candidates, < 5ms."

WHY PARALLEL QUERIES FOR COMBINED SYSTEMS
"Driver search (Redis) and place search (PostgreSQL) are independent — run in parallel,
 merge at the BFF. Trying to unify them in one query would couple two separate storage
 systems and make each slower."

HISTORY DB PURPOSE
"Driver location history is in PostgreSQL for audit, trip replay, and dispute resolution.
 It's written asynchronously via Kafka — never in the driver update request path."
Why: 250K writes/sec is too fast for synchronous PostgreSQL; and the history is only
needed for lookups, not real-time dispatch.
```

---

## Part 23: Stress Test Questions

These are the hardest questions an interviewer might ask. If you can answer them, you
are well-calibrated for Senior SWE for this problem.

**"What happens if a city has a major event (concert, sports game) that attracts 50,000
drivers to a 1km area? How does your system behave?"**

The drivers:available ZSET for this area gets 50,000 GEOADD operations in a 30-minute
window as drivers converge. Each driver sends 1 update every 4 seconds = 50,000 / 4 =
12,500 GEOADD/second for that one zone, on top of baseline traffic. If the entire Redis
Cluster handles 200K ops/second across 6 nodes, 12,500 extra ops for one zone is a 6%
capacity increase — manageable without special handling.

For GEORADIUS: querying this zone returns 50,000 candidates within 1km (instead of the
usual 50-200). Redis processes 50,000 results in < 10ms (it's just a ZRANGEBYSCORE +
filter). The response size is larger (50,000 driver objects), but dispatch only needs
the top 10 nearest — use `COUNT 10` to limit the response immediately.

**"GeoHash precision 5 gives cells of ~4.9km × 4.9km. Your user searches within 3km.
The 9-cell query covers 14.7km × 14.7km. Isn't that too many false positives?"**

Yes, the bounding box is 216 km² for a 28 km² circle (3km radius). False positive rate:
(216 - 28) / 216 = ~87% of candidates are outside the circle. For typical city density
(100 places/km²), the 3km circle has ~2,800 places, but the query returns 21,600
candidates. Haversine filtering is O(N) with very fast arithmetic — filtering 21,600
rows takes < 10ms in-memory. The DB I/O (reading 21,600 rows from the index) is the
bottleneck, not the filter. To reduce I/O: use a smaller precision. Precision 6 gives
9 cells covering 3.6km × 1.8km = 6.48 km² for the same 3km search — much better.
But precision 6 has the boundary problem for larger radii. The correct answer: use
precision 6 for radii ≤ 1km, precision 5 for 1-5km, and accept the false-positive overhead
at larger radii as an acceptable tradeoff for simplicity.

**"A driver spams location updates (100 updates/second instead of 0.25). How does this
affect the system?"**

100 updates/second × 1 driver = 100 extra GEOADD/second. Negligible. But 100 update-spamming
drivers × 100 updates/second = 10,000 extra GEOADD/second. Still manageable.

Rate limit driver location updates at the API gateway: max 1 update per 3 seconds per
driver. If a driver sends faster, return 429 Too Many Requests and drop the update.
Redis never sees the overflow. Implement via a Redis counter per driver_id with EX 3.

**"How would you implement 'search places open right now'?"**

Add an `hours_json` column to the places table storing opening hours as JSON:
```json
{
  "monday": [{"open": "09:00", "close": "22:00"}],
  "tuesday": [...],
  ...
}
```

At query time: compute the current day and time (server-side, in the user's timezone).
Convert to a simple boolean "is open now" per place — this is a pure computation, not
a DB filter. The GeoHash query returns candidates; the application filters by "is open now"
in-memory. This adds ~1ms of computation for 100-900 candidates.

Do NOT try to index by opening hours in the DB — it's a complex recurring schedule, not
a simple range. Compute it in the application layer from the stored JSON.

---

## Part 19: Complete Request Flow Walkthroughs

### 19.1 Place Search — Request by Request

Walk through a complete "find nearby restaurants within 2km" request.

```
REQUEST:  GET /api/v1/places/search?lat=37.782&lng=-122.414&radius=2000&category=restaurant
          User is at lat 37.782, lng -122.414. Wants restaurants within 2km.

STEP 1: API Server receives request
  - Validate inputs: lat in [-90, 90], lng in [-180, 180], radius in [0, 50000]
  - Determine GeoHash precision: radius ≤ 2000m → precision 6

STEP 2: Encode query center to GeoHash
  center_hash = geohash_encode(37.782, -122.414, precision=6)
  Result: "9q8yy8"   (example — actual value depends on encoding library)

STEP 3: Compute 8 neighbor cells
  neighbors = geohash_neighbors("9q8yy8")
  Result: ["9q8yy9", "9q8yyc", "9q8yyf", "9q8yyb", "9q8yy5",
           "9q8yy4", "9q8yy6", "9q8yy7"]
  All 9 cells (center + 8 neighbors)

STEP 4: Query PostgreSQL
  SELECT place_id, name, category, lat, lng, rating, rating_count
  FROM places
  WHERE geohash_6 = ANY(ARRAY['9q8yy8', '9q8yy9', ..., '9q8yy7'])
    AND category = 'restaurant'
    AND is_deleted = FALSE
  ORDER BY rating DESC   ← rough pre-sort, exact sort after filter
  LIMIT 500              ← cap candidates; 500 is enough for any reasonable density

  Result: 73 candidate restaurants from the 9 cells

STEP 5: Haversine filter
  For each of 73 candidates:
    d = haversine(37.782, -122.414, candidate.lat, candidate.lng)
    if d <= 2000:  keep candidate
  Result: 51 restaurants within exact 2km circle

STEP 6: Attach distance and sort
  For each of 51 results: compute exact distance
  Sort by: (rating DESC, distance ASC) — most practical sort for a restaurant list
  Paginate: return first 20, generate cursor for page 2

STEP 7: Return response
  JSON with 20 restaurant objects + next_cursor
  Total server-side time: ~15ms
  PostgreSQL query (with index): ~5ms
  Haversine filter (51 items): < 1ms
  Serialization + network: ~10ms

TOTAL END-TO-END: ~30ms. Well within 100ms p99 SLO.
```

### 19.2 Driver Location Update — Request by Request

Walk through a complete driver location update.

```
REQUEST:  PUT /api/v1/drivers/d_456/location
          Body: { "lat": 37.780, "lng": -122.413, "heading": 45, "status": "available" }
          Driver d_456 is sending their 4-second GPS update.

STEP 1: API Server receives request
  - Validate driver_id (check driver:meta exists or JWT token)
  - Validate lat/lng range
  - Rate limit: check driver:ratelimit:{driver_id} in Redis
    INCR driver:ratelimit:d_456 / SET EX 3 if new
    If count > 1 within 3s window: return 429 (driver is spamming updates)

STEP 2: Write to Redis GEO (synchronous, in request path)
  GEOADD drivers:available -122.413 37.780 d_456
  SET driver:ttl:d_456 1 EX 30

  If status == "offline":
    ZREM drivers:available d_456
    DEL driver:ttl:d_456
  If status == "on_trip":
    ZREM drivers:available d_456
    GEOADD drivers:on_trip -122.413 37.780 d_456

STEP 3: Write to Redis Hash for metadata (synchronous)
  HMSET driver:meta:d_456 heading 45 speed_kph 35 lat 37.780 lng -122.413
  EXPIRE driver:meta:d_456 60

STEP 4: Publish to Kafka (asynchronous, fire-and-forget)
  Topic: location_updates
  Message: { driver_id: d_456, lat: 37.780, lng: -122.413, heading: 45,
             ts: 2026-06-25T14:22:01Z }
  The Kafka publish is async — the response does NOT wait for Kafka ACK.

STEP 5: Return response
  HTTP 200 OK, empty body

TOTAL SERVER-SIDE TIME: ~5ms
  Redis GEOADD: ~1ms
  Redis SET: ~1ms  
  Redis HMSET + EXPIRE: ~1ms
  Kafka publish (async): 0ms (non-blocking)
  Total: ~3-5ms. Within 50ms p99 SLO.
```

### 19.3 Driver Search — Request by Request

Walk through a complete "find available drivers near me" request.

```
REQUEST:  GET /api/v1/drivers/nearby?lat=37.782&lng=-122.414&radius=2000
          Rider wants to see available drivers within 2km.

STEP 1: API Server receives request
  - Validate inputs
  - No authentication required for this read (public endpoint with rate limiting)

STEP 2: Query Redis GEO
  GEOSEARCH drivers:available
    FROMLONLAT -122.414 37.782
    BYRADIUS 2 km
    ASC
    COUNT 10
    WITHCOORD
    WITHDIST

  Result: 8 drivers returned with distances and coordinates

STEP 3: Fetch driver metadata
  For each of 8 driver_ids:
    HGETALL driver:meta:{driver_id}
  (Can pipeline all 8 HGETALLs in a single Redis round-trip)

  Result: heading, speed_kph, vehicle_type for each driver

STEP 4: Build and return response
  Combine GEOSEARCH results (lat, lng, distance) with metadata (heading, vehicle_type)
  Return JSON with 8 driver objects

TOTAL SERVER-SIDE TIME: ~8ms
  GEOSEARCH: ~3ms (1M member ZSET, 2km radius, ~8 results)
  8 HGETALL (pipelined): ~2ms
  Serialization: ~1ms
  Network: ~5ms
  TOTAL END-TO-END: ~10-15ms. Well within 50ms p99 SLO.
```

---

## Part 20: Scaling Deep Dive — What Breaks and When

### 20.1 The Place Search Bottleneck

At which user scale does PostgreSQL stop being sufficient for place search?

```
PostgreSQL performance cliff analysis:
  Indexed GeoHash query: ~5ms per query
  Single PostgreSQL node: ~5,000 indexed queries/second peak
  
  When does single node fail?
  5,000 QPS / 10 searches per user per day = 5,000 QPS × 86,400 / 10 = 43.2M DAU
  
  → At > 43M DAU, a single PostgreSQL primary becomes the bottleneck.
  → Solution: add read replicas. Each replica handles 5,000 QPS.
  → With 10 read replicas: handle 430M DAU (more than most apps ever reach)
  
  PostgreSQL horizontal read scaling is the right approach for place search.
  Write scaling: new places are rare — 1 primary handles millions of DAU.
```

### 20.2 The Driver Location Bottleneck

At which driver count does a single Redis instance become the bottleneck?

```
Redis single-instance throughput: 200,000 GEOADD/second

Each driver: 1 GEOADD + 1 SET per update = 2 ops per 4 seconds = 0.5 ops/second
  Single Redis node handles: 200,000 / 2 = 100,000 drivers (at full capacity)
  With 50% headroom: 50,000 drivers per Redis node

Scale milestones:
  50,000 drivers:  1 Redis node
  250,000 drivers: 5 Redis nodes → Redis Cluster
  1,000,000 drivers: 20 Redis nodes → geo-partitioned cluster (us-west, us-east, etc.)
  10,000,000 drivers: 200 Redis nodes → each city is its own Redis Cluster

The inflection point (when to go from single Redis to Redis Cluster) is around
50,000-100,000 concurrent drivers. If your platform is smaller than this, start with
a single Redis primary + replica. Premature sharding adds operational complexity.
```

### 20.3 When GeoHash Becomes the Bottleneck

GeoHash search performance degrades when:
1. The search radius is very large (> 50km), requiring hundreds of cells
2. A single GeoHash cell has millions of places (extreme density)

For case 1: cap the search radius in the API (50km max). At > 50km, the use case changes
from "nearby" to "regional search" — different product feature, different algorithm.

For case 2: PostGIS with an R-tree spatial index handles extreme density better than
GeoHash + B-tree, because the R-tree adapts its partitioning to data density. At extreme
density (e.g., 1M businesses in Manhattan), PostGIS is the right production tool.
For L5 interviews: GeoHash is the correct conceptual answer. PostGIS is the production answer.

---

## Exercises

**Exercise 1 — GeoHash Precision Selection**
You are building a "find nearby events" feature. Events can be searched at distances of
500m, 2km, 5km, and 20km. For each search radius, specify:
(a) The GeoHash precision to use
(b) The approximate cell size at that precision
(c) The approximate number of cells to query (hint: 9 for most radii)
(d) The approximate number of candidate rows before Haversine filtering (assume 100 events
    per precision-6 cell in a dense city)

**Exercise 2 — Driver Update Rate**
Your app has 500K drivers globally.
(a) If each driver updates every 5 seconds, what is the average GEOADD rate?
(b) During evening rush (3× average), what is the peak rate?
(c) A single Redis instance handles 150,000 ops/sec. How many Cluster primary nodes do
    you need for peak traffic, with 50% headroom?
(d) If you switch to updates every 2 seconds (higher accuracy), what changes architecturally?

**Exercise 3 — Bounding Box vs Circle**
The GeoHash 9-cell query returns a rectangular bounding box of candidates.
(a) For 2km radius search with precision-6 cells (1.2km × 0.6km): what is the area of
    the 3×3 bounding box vs the area of the search circle?
(b) What percentage of bounding box candidates are outside the circle?
(c) Is the extra Haversine filter computation expensive? Justify with numbers.
(d) How does this ratio change with precision-5 cells (4.9km × 4.9km) for the same radius?

**Exercise 4 — Driver Redis Failure**
The Redis Cluster primary node for one keyslot range fails. Promotion takes 15 seconds.
(a) What does the driver location service return during the 15-second window?
(b) What does a rider see?
(c) Design a graceful degradation strategy (no error message to user).
(d) If the entire Redis Cluster is lost, what is the fallback?

**Exercise 5 — GeoHash Boundary Bug**
A place at lat 37.7999, lng -122.0001 has geohash_6 = "9q9p40". A user at lat 37.8001,
lng -122.0001 (just 22 meters away, on the other side of the cell boundary) runs a 1km
search. Their computed center cell is "9q9p41". The 9-neighbor set is [9q9p41 + 8 neighbors].
Does it include "9q9p40"? Draw the answer.

**Exercise 6 — Rate Limiting Driver Updates**
A driver app has a bug and sends 50 location updates per second instead of 0.25.
(a) Describe a Redis-based rate limiter for driver updates (max 1 update per 3 seconds per driver)
(b) What Redis key structure would you use?
(c) What happens to the over-limit updates? (Accept/reject/queue?)
(d) At what number of buggy drivers does this become a Redis bottleneck?

**Exercise 7 — TTL Design**
You are choosing between these two driver TTL approaches:
  A. Keyspace notifications: driver:ttl:{id} with EX 30; on expiry, ZREM driver
  B. Scheduled cleanup job: every 30 seconds, ZRANGE over all drivers, check which
     have no recent update, ZREM the stale ones
(a) What is the maximum stale-driver window for each approach?
(b) Which approach is more reliable? Why?
(c) Design approach B's cleanup job pseudocode. What is its Redis complexity?
(d) Which would you use in production? Why (hint: combine both)?

---

## Homework

**Homework 1 — GeoHash Neighbor Lookup**
Using the `python-geohash` library (or equivalent):
- Write a function `nearby_cells(lat, lng, radius_m) → list[str]` that returns the 9
  GeoHash cells covering the search area, choosing precision based on the radius
- Test with your city's coordinates at radius 500m, 2km, 5km
- Verify by plotting cell bounds on a map (geohash.org has a viewer)

**Homework 2 — Redis GEO Playground**
Set up a local Redis instance:
- GEOADD 20 fake driver locations around a city
- GEOSEARCH to find drivers within 2km from different query centers
- Simulate driver offline: SET driver:ttl:d1 1 EX 5; wait for expiry; observe the driver
  is STILL in the ZSET (ZREM isn't hooked up) — this demonstrates why the keyspace
  notification handler is necessary
- Measure GEOSEARCH latency for 20 vs 1,000 vs 100,000 fake drivers

---

## Part 21: Glossary of Key Terms

**Bounding box**: The smallest rectangle (in lat/lng space) that contains a circular search
area. Used internally by Redis GEORADIUS and GeoHash 9-cell query as an approximation
before the exact Haversine filter. The bounding box is always larger than the circle,
producing false positive candidates that are discarded by the filter step.

**GeoHash**: A hierarchical spatial data structure that divides the Earth into a grid of
rectangular cells and assigns each a hash code string. Nearby cells share a common prefix.
Precision (string length) controls cell size: precision 5 = ~4.9km × 4.9km, precision
6 = ~1.2km × 0.6km.

**GEOADD**: Redis command. `GEOADD key lng lat member`. Adds a geospatial member to a sorted
set with a geospatial score encoded as a 52-bit integer. O(log N).

**GEORADIUS / GEOSEARCH**: Redis command for spatial radius search. `GEORADIUS key lng lat
radius unit COUNT max_results ASC WITHCOORD WITHDIST`. Internally: ZRANGEBYSCORE on
bounding-box score range, then Haversine filter. GEORADIUS is deprecated in Redis 6.2;
use GEOSEARCH (same semantics, more options).

**Haversine formula**: A formula for computing great-circle distance between two points on a
sphere given their lat/lng coordinates. Accounts for Earth's curvature. More accurate than
Euclidean distance for large distances; for nearby points (< 100km), the difference from
Euclidean is negligible but Haversine is still preferred for correctness.

**Keyspace notification**: A Redis feature where Redis publishes events (key expiry, set,
delete) to a pub/sub channel. Subscribers can react to events like "this key expired."
Used here to trigger ZREM when a driver's TTL key expires. Must be enabled with
`notify-keyspace-events Ex` in Redis configuration.

**PostGIS**: A PostgreSQL extension that adds native `GEOMETRY` and `GEOGRAPHY` types with
spatial operations (ST_DWithin, ST_Distance, etc.) and spatial indexes (GiST R-tree). More
accurate than GeoHash for true circle queries; handles the boundary problem natively.

**Precision**: In the context of GeoHash, the number of characters in the hash string.
More characters = smaller cell = more precise location. Precision 6 hash `"9q8yy9"` locates
a point to within ~1.2km × 0.6km. Precision 9 locates it to ~5m × 5m.

**Redis Cluster**: A horizontally sharded Redis deployment where keyspace is partitioned
into 16,384 hash slots distributed across multiple primary nodes. Provides automatic
failover, horizontal write scaling, and increased total memory capacity.

**Spatial index**: A data structure for efficient querying of geometric data. Examples: R-tree
(PostGIS), GiST index, GeoHash string index (PostgreSQL), ZSET geospatial encoding (Redis).
The key property: nearby points are stored near each other in the index, enabling fast
range queries without scanning the entire dataset.

---

## Part 20: Frequently Misunderstood Concepts

### 20.1 "GeoHash Is Not the Same as a Grid Search"

A common misconception: "GeoHash is just dividing the map into a grid." That's partially
right, but the key insight is that GeoHash's string representation encodes the grid position
in a way that enables standard string prefix matching. You don't need a 2D spatial index
to find places in a cell — you just need a B-tree index on a VARCHAR column.

```
Naive grid approach:
  cells are identified by (row, col) tuples
  finding cells: need 2D lookup or custom spatial structure
  storage: need a spatial index

GeoHash approach:
  cells identified by a string prefix
  finding cells: string prefix match on a B-tree index ← standard SQL, no extension needed
  storage: just add a VARCHAR column to your existing table
```

GeoHash makes spatial search accessible without PostGIS — a huge practical benefit for
teams that don't want to manage a PostGIS installation.

### 20.2 "GEORADIUS Returns Exact Results"

Not quite. GEORADIUS returns results within the radius to within a small margin of error
(0.6% of the distance) due to the internal 52-bit integer encoding. For all practical
purposes in ride dispatch or place search, 0.6% error on a 2km radius = 12m error —
completely acceptable. Never claim GEORADIUS is exact — it's highly accurate but not
precise to centimeters.

### 20.3 "Redis Keyspace Notifications Are Reliable"

Redis keyspace notifications are at-most-once delivery. If the subscriber is down when
the expiry event fires, the event is lost. The driver stays in the ZSET as a "ghost"
until the next cleanup pass.

For production: combine keyspace notifications with a periodic cleanup job (every 60
seconds, scan for drivers with no recent `driver:ttl:{id}` key and ZREM them). The
keyspace notification provides fast (~30ms) removal; the periodic job is the safety net
for missed notifications.

### 20.4 "250K Writes/Second Is Too Fast for Any Database"

Not true — it's too fast for a standard OLTP PostgreSQL setup, but manageable for
specialized stores. Redis handles it (200K+/sec per node). Cassandra handles it (100K+/sec
per node with wide-column schema). InfluxDB handles it (100K+/sec for time-series). The
lesson: match the storage tier to the write pattern, not the other way around. The mistake
is trying to shoehorn high-write-rate spatial data into a general-purpose relational DB
that was designed for transactional consistency, not throughput at this scale.

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════╗
║      CHAPTER 74: LOCATION-BASED SERVICE (L5) KEY TAKEAWAYS          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  1. GEOHASH = 2D COORDINATES → 1D STRING PREFIX                     ║
║     Nearby points share a prefix. Query center cell + 8 neighbors   ║
║     (9 cells). Haversine-filter candidates to exact circle.         ║
║     Precision 6 for ≤ 1km; precision 5 for ≤ 5km radius.           ║
║                                                                      ║
║  2. TWO STORAGE TIERS FOR TWO WORKLOADS                              ║
║     Places (static, read-heavy): PostgreSQL + GeoHash index.        ║
║     Drivers (dynamic, write-heavy): Redis GEO Cluster.              ║
║     The architectural split is justified by the data characteristics.║
║                                                                      ║
║  3. DRIVER WRITE RATE = 250K GEOADD/SECOND                          ║
║     1M drivers × 0.25 updates/sec = 250K writes/sec.               ║
║     Exceeds single Redis node (200K ops/sec).                       ║
║     Redis Cluster with 4+ primary nodes handles this.               ║
║                                                                      ║
║  4. PER-DRIVER TTL: SEPARATE KEY + KEYSPACE NOTIFICATION            ║
║     Redis ZSET has no per-member TTL.                               ║
║     Use driver:ttl:{id} with EX 30.                                 ║
║     On expiry: keyspace notification → ZREM from available ZSET.    ║
║                                                                      ║
║  5. REDIS GEO IS A SORTED SET UNDERNEATH                            ║
║     GEOADD = ZADD with 52-bit geospatial score.                     ║
║     GEORADIUS = bounding-box ZRANGEBYSCORE + Haversine filter.      ║
║     O(N + log M) time; < 5ms for 1M members, 2km radius.           ║
║                                                                      ║
║  6. PARALLEL QUERIES FOR COMBINED SYSTEMS                            ║
║     Serve driver search (Redis) and place search (PostgreSQL)        ║
║     as independent parallel queries. Merge at the client or BFF.    ║
║                                                                      ║
║  7. SCOPE CLEARLY: WHAT L5 DOESN'T REQUIRE                         ║
║     Routing, traffic, multi-region geo-routing, ML ranking.         ║
║     Stating these as out-of-scope signals L5 calibration.           ║
║                                                                      ║
║  ONE-SENTENCE SUMMARY:                                               ║
║  "Location-based service = GeoHash-indexed PostgreSQL for static    ║
║   place search + Redis GEO Cluster (GEORADIUS) for 250K/sec        ║
║   driver updates, with per-driver 30s TTL via keyspace events."    ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

### Quantitative Exercises

**Quantitative Exercise 1 — GeoHash Precision Selection**
You are building a "find nearby events" feature. Events can be searched at distances of
500m, 2km, 5km, and 20km. For each radius, specify:
(a) The GeoHash precision to use
(b) The approximate cell size at that precision
(c) The approximate number of cells to query (hint: 9 for small radii)
(d) The approximate candidate count before Haversine filtering (assume 100 events per
    precision-6 cell in a dense city)

**Quantitative Exercise 2 — Driver Write Rate**
Your app has 500K drivers globally.
(a) If each driver updates every 5 seconds, what is the average GEOADD rate?
(b) During evening rush (3× average), what is the peak rate?
(c) A single Redis node handles 150,000 ops/sec. How many Cluster nodes with 50% headroom?
(d) If you switch to 2-second updates for higher accuracy, what changes in the architecture?

**Quantitative Exercise 3 — Bounding Box vs. Circle**
The GeoHash 9-cell query returns a rectangular bounding box.
(a) For a 2km radius search with precision-6 cells (1.2km × 0.6km): what is the area of
    the 3×3 bounding box vs. the area of the search circle?
(b) What percentage of bounding box candidates are outside the circle?
(c) Is the extra Haversine filter computation expensive? Justify with numbers.

**Quantitative Exercise 4 — Driver Redis Failure**
The Redis Cluster primary node for the "us-west" region fails. Promotion takes 15 seconds.
(a) What does the driver location service return during the 15-second window?
(b) What does a rider see in the app?
(c) Design a graceful degradation strategy that avoids showing an error.

---

### Quick Reference: Key Numbers to Memorize

Before the interview, know these numbers cold. An interviewer who asks "how fast can
Redis handle driver updates?" expects a number, not "Redis is fast."

```
REDIS GEO PERFORMANCE:
  GEOADD:         < 1ms per call; ~200,000 ops/second per node
  GEORADIUS:      < 5ms for 1M members, 2km radius, ~100 candidates
  GEOSEARCH:      Same performance as GEORADIUS (GEORADIUS is deprecated)
  Memory per entry: ~60-90 bytes (ZSET overhead + member string)

GEOHASH CELL SIZES:
  Precision 5: ~4.9km × 4.9km  → use for 1-5km radius searches
  Precision 6: ~1.2km × 0.6km  → use for ≤ 1km radius searches
  Precision 7: ~152m × 152m    → use for ≤ 0.2km radius searches

DRIVER UPDATE RATE:
  1M drivers × (1 update / 4 seconds) = 250,000 GEOADD/second
  Single Redis node max: ~200,000 ops/second → need Redis Cluster
  Redis Cluster with 4 primary nodes: ~800,000 ops/second capacity

POSTGRESQL PLACE SEARCH:
  GeoHash indexed query: ~5ms per query
  Single node capacity: ~5,000-10,000 queries/second
  At 10M DAU × 10 searches/day: need 2 read replicas at peak

CANDIDATE COUNTS:
  Precision-6 cell (1.2km × 0.6km) in a dense city: ~50-200 places
  9-cell query: ~450-1,800 candidates before Haversine filter
  After filter (2km circle): ~20-100 results matching

MEMORY:
  100M users × 200 driver feed entries: only for news feed (not applicable here)
  1M drivers × ~90 bytes = 90 MB Redis memory — trivial
  500M places × 200 bytes = 100 GB PostgreSQL storage
```

---

## Part 24: 5-Minute Interview Simulation

Practice the opening 5 minutes of this interview cold, then check your answer against this model.

**The question you'll receive:**
"Design a service that allows users to find nearby restaurants, and also allows our driver
tracking platform to show riders where the nearest available drivers are."

**What you say in the first 5 minutes (model answer):**

"Before I start drawing, a few quick clarifications:
1. For the place search — static business data like restaurants, or dynamic POIs that
   change in real time? [Interviewer: static restaurants.]
2. For driver tracking — how many concurrent active drivers? [Interviewer: up to 1M.]
3. What's the target search radius? [Interviewer: places up to 5km, drivers up to 3km.]
4. Consistency requirements? Can a newly added restaurant take a minute to appear?
   [Interviewer: yes, eventual is fine for places.]
5. Availability vs consistency tradeoff for driver locations? [Interviewer: availability —
   it's okay if a driver is occasionally slightly stale.]

Okay, I'll design two subsystems that share an architecture:
- **Place Search**: static data, read-heavy. I'll use PostgreSQL with a GeoHash-indexed
  column. Query center cell + 8 neighbors (9 cells), Haversine filter. O(log N) lookup.
- **Driver Location**: dynamic data, write-heavy. 1M drivers × 0.25 updates/sec = 250K
  writes/second. PostgreSQL can't handle that write rate. I'll use Redis GEO — GEOADD
  for updates, GEORADIUS for nearby search. Redis Cluster with ~4 nodes for throughput.
- **Shared principle**: both use spatial locality for efficient queries. The storage tier
  differs because their write/read ratios are opposite.

Let me draw the two write paths and two read paths..."

**What this opening signals to the interviewer:**
- You know to clarify before designing (maturity)
- You identified the key constraint immediately (250K writes/sec → can't use PostgreSQL)
- You named the two tools correctly (PostgreSQL + Redis GEO)
- You justified the split in one sentence
- You're ready to dig into details

**What a weak opening looks like:**
"I'd store restaurant locations in a database with lat and lng columns, and use a spatial
index to do the search..." — correct direction but no driver tracking, no scale awareness,
no Redis GEO.

---

## Part 25: SSE Brainstorming Reference

The key decision tree for location-based service design:

```
LOCATION QUERY TYPE?
       │
       ├── Static objects (places, POIs)?
       │       │
       │       └── Write frequency: low (updates daily or less)
       │           Read frequency: millions/day
       │           → PostgreSQL + GeoHash string index
       │             OR PostgreSQL + PostGIS ST_DWithin
       │           → Read replicas for scale
       │
       └── Dynamic objects (drivers, users, vehicles)?
               │
               └── Write frequency: HIGH (multiple times per second per object)
                   Read frequency: lower (query on demand)
                   → Redis GEO (GEOADD + GEORADIUS/GEOSEARCH)
                   → Redis Cluster for > 50K concurrent objects
                   → Per-object TTL via separate key + keyspace notification

SEARCH RADIUS?
       │
       ├── ≤ 1km → GeoHash precision 6 (1.2km × 0.6km cells)
       ├── ≤ 5km → GeoHash precision 5 (4.9km × 4.9km cells)
       └── > 5km → Precision 4 OR PostGIS (more efficient for large radii)

ALWAYS: Query 9 cells (center + 8 neighbors). Haversine filter the results.

DRIVER MATH:
  drivers_per_node = node_capacity / updates_per_driver_per_second
  node_capacity = 200,000 ops/sec; updates = 0.25/sec
  drivers_per_node = 200,000 / (0.25 × 2 ops/update) = 400,000 drivers/node (theoretical)
  In practice with overhead: ~100,000 drivers/node at 50% utilization
  At 1M drivers: 10 Redis Cluster nodes

PLACE MATH:
  place_search_qps = DAU × searches_per_day / 86,400
  10M DAU × 10 searches = 100M searches/day = 1,157 QPS average
  Peak (5×): 5,785 QPS
  PostgreSQL read replica handles 5,000-10,000 QPS → 2 replicas for peak
```

---

## What to Read Next

- **Ch101 — Location and Maps (Staff)**: The same system at full L6 depth. Adds
  multi-region geo-routing, S2 geometry library (Google's alternative to GeoHash),
  real-time traffic ingestion, and ML-based ETA estimation.
- **Ch63 — Proximity Service**: Focused purely on static place search with detailed
  GeoHash theory, QuadTree comparison, and PostGIS spatial index deep-dive.
- **Ch68 — Ride Sharing**: The ride dispatch system that consumes the driver location
  data this chapter produces. Driver matching, surge pricing, ETA calculation.
- **Ch47 — Consistent Hashing**: How Redis Cluster distributes driver data across nodes.
  When a Redis node is added or removed from the Cluster, consistent hashing determines
  which keyslots (and therefore which driver location data) move to the new node.
- **Ch65 — Key-Value Store**: Redis internals (ZSET skip list + hash table), relevant
  to understanding GEO command performance characteristics. GEO commands are implemented
  as ZADD/ZRANGEBYSCORE with a specialized score encoding — understanding ZSET internals
  gives you a foundation for estimating GEORADIUS time complexity.
- **Ch50 — Rate Limiter**: The driver location update rate limiter (max 1 update per
  3 seconds per driver) uses the same token-bucket or fixed-window counter pattern
  described in Ch50. Redis INCR + EXPIRE is the implementation primitive.
- **Ch51 — Distributed Cache**: Redis Cluster's consistent hashing and hot-key detection
  are described in detail in Ch51, which provides the theoretical foundation for the
  Redis sharding strategy used in this chapter.

### Pre-Interview Final Checklist

The night before your interview, run through this checklist. If you can't answer any item
in under 30 seconds, review the relevant section.

```
SPATIAL INDEXING:
[ ] Explain GeoHash in one sentence
[ ] Name the precision level for 1km, 5km radius search
[ ] Draw the 3×3 neighbor grid
[ ] Explain why 9 cells, not 1
[ ] Explain the Haversine filter step

REDIS GEO:
[ ] Name the write command: GEOADD
[ ] Name the read command: GEOSEARCH (or GEORADIUS)
[ ] Explain GEORADIUS internal structure (ZSET + bounding box + Haversine)
[ ] State the per-driver TTL approach (separate key + EX 30 + keyspace notification)
[ ] Explain why keyspace notifications need a backup cleanup job

STORAGE SPLIT:
[ ] State which storage tier each data type uses (places → PostgreSQL, drivers → Redis)
[ ] Justify the split in one sentence (write rate + query type mismatch)
[ ] State when you'd switch from single Redis to Redis Cluster (> 50K drivers)

CAPACITY:
[ ] Calculate: 1M drivers × 0.25 updates/sec = 250K GEOADD/sec
[ ] State: single Redis node max ~200K ops/sec → need Redis Cluster
[ ] State: 10M DAU × 10 searches/day → ~1,160 QPS average for place search
[ ] State: 2 PostgreSQL read replicas handle place search peak traffic

OUT OF SCOPE:
[ ] Can clearly state: routing, turn-by-turn navigation, multi-region, ML ranking
[ ] Can explain WHY each is out of scope (different system, different complexity level)
```

---

*Chapter 74 — Section 5: Senior SWE L5 Case Studies.*
*Pairs with: Ch101 (Location Staff), Ch63 (Proximity Service), Ch68 (Ride Sharing).*
*Target depth: L5 single-region. Out of scope: routing, multi-region, ML ranking.*
*Core concepts: GeoHash 9-cell query, Redis GEOADD/GEORADIUS, driver TTL, 250K writes/sec.*
*Two subsystems: PostgreSQL + GeoHash index (places), Redis GEO Cluster (driver tracking).*
*Key numbers: 250K GEOADD/sec for 1M drivers; 2 PostgreSQL replicas for 10M DAU search;*
*per-driver TTL via driver:ttl:{id} EX 30 + keyspace notification → ZREM from available ZSET.*
*GeoHash precision: 6 for ≤ 1km radius, 5 for ≤ 5km radius. Always query 9 cells.*
*Redis GEO internal: ZSET with 52-bit geospatial score. GEORADIUS = ZRANGEBYSCORE + Haversine.*
*GEOADD argument order: key lng lat member (longitude before latitude — a common bug source).*
*Rate limit driver updates: max 1 per 3 seconds per driver via Redis INCR + EX 3.*
*Two reads per ride request: GEORADIUS (drivers) + PostgreSQL GeoHash (places) run in parallel.*
*Driver offline detection: 30s TTL, not polling — keyspace notification fires on expiry.*
*Hot cell handling: Times Square with 500 drivers → 125 writes/sec to one zone, < 0.1% of node capacity.*
*Last updated: 2026-06-25. Written by Claude for Ranjeet Singh Negi's L5 interview prep.*

## Interview Simulation — Location-Based Service L5

*45-minute system design interview. Phases follow the Section 2 framework: Requirements → Estimation → API → Data Model → HLD + Deep Dive.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a location-based service — think the driver tracking and nearby search backend for a ride-sharing app. Where do you start?

**Candidate:** Two subsystems with very different access patterns. Let me confirm scope. First: driver tracking — real-time location updates from active drivers, maybe 250,000 drivers on the road at peak. Second: place/driver search — given a user's coordinates, find nearby drivers or points of interest within a radius.

> **Interviewer:** Yes, both. Drivers update their location continuously. Riders need to see nearby drivers within ~3 km.

**Candidate:** A few questions. How frequently do drivers send location updates?

> **Interviewer:** Every 4 seconds per driver.

**Candidate:** What's the search radius for nearby drivers?

> **Interviewer:** 3 km radius, return top 10 nearest available drivers.

**Candidate:** Do we need location history — like, can a rider replay the trip route after the ride ends?

> **Interviewer:** Yes, save location history for post-trip replay and audit.

**Candidate:** Is this single-region?

> **Interviewer:** Yes. Single region.

**Candidate:** Scope: real-time driver location in Redis GEO structures (write-heavy, current location only), location history to Kafka → PostgreSQL (write-once, never queried live), and GeoHash-based search for nearby drivers. I'll skip routing, ETA, and multi-region. That good?

> **Interviewer:** Perfect.

*(Cross-question: two-subsystem framing)* Calling out current location vs history storage immediately shows senior design thinking. They're different SLOs, different tier choices.

---

### Phase 2: Estimation (4 min)

> **Interviewer:** Run the numbers.

**Candidate:** Driver update write rate: 250,000 active drivers × 1 update per 4 seconds = 62,500 writes/sec. That's the peak write throughput our location store must handle.

Each location record: driver_id (8 bytes) + lat/lng (16 bytes) + timestamp (8 bytes) = 32 bytes. Location history: 62,500 writes/sec × 32 bytes = 2 MB/sec raw, or 172 GB/day. Via Kafka to PostgreSQL, partitioned by driver_id.

Redis GEO storage for current locations: 250,000 drivers × 72 bytes per GEO entry (internal ZSET encoding) ≈ 18 MB. Trivially fits in Redis memory. Single-node could handle it, but we use a 3-shard cluster for write throughput (each shard handles ~21K writes/sec, well under Redis's ~100K/sec limit per node).

Rider search rate: 1M DAU riders, each requests nearby drivers every 10 seconds when in-app = 100,000 GEORADIUSBYMEMBER calls/sec at peak. These are read-heavy, served from Redis with sub-millisecond latency.

> **Interviewer:** Why is 62,500 writes/sec scary for a relational database?

**Candidate:** PostgreSQL handles ~10,000 simple writes/sec comfortably, ~30,000 with connection pooling and optimized schemas. At 62,500 writes/sec you'd need heavy sharding, and each write updates a row for the driver — causing hot row lock contention. Redis GEO is purpose-built for this: `GEOADD` is O(log N), no locking, and each node handles 100K ops/sec. Wrong tool = outage at peak.

---

### Phase 3: API Design (4 min)

> **Interviewer:** What are the key APIs?

**Candidate:** Three endpoints: driver location update, nearby driver search, and place search.

**Driver location update (driver-side, called every 4 seconds):**
```
POST /drivers/{driver_id}/location
Authorization: Bearer {driver_token}
Body: { latitude: 37.7749, longitude: -122.4194, timestamp: 1719360000 }
Response: 204 No Content
```

**Nearby drivers search (rider-side):**
```
GET /drivers/nearby?lat=37.7749&lng=-122.4194&radius_km=3&limit=10
Authorization: Bearer {rider_token}
Response: {
  drivers: [
    { driver_id, latitude, longitude, distance_km, vehicle_type, rating }
  ]
}
```

**Place search:**
```
GET /places/nearby?lat=37.7749&lng=-122.4194&radius_km=5&category=restaurant&limit=20
Response: {
  places: [ { place_id, name, lat, lng, distance_km, category } ]
}
```

> **Interviewer:** Should the driver update be POST or PUT?

**Candidate:** Semantically, PUT is more correct — you're replacing the current known location for this driver. But POST works fine since the body is interpreted as "add a new location sample." In practice, the HTTP verb doesn't matter much here; what matters is idempotency. A driver sending the same location twice should not create duplicates. Using driver_id as the key in GEOADD means re-sending the same coordinates just overwrites the existing entry — naturally idempotent regardless of verb.

---

### Phase 4: Data Model (4 min)

> **Interviewer:** Walk me through storage design.

**Candidate:** Three tiers: Redis GEO for current driver positions, PostgreSQL for places and location history, Kafka as the durable buffer between write path and PostgreSQL.

**Redis GEO Cluster — current driver locations:**
```
Key:    drivers:active
Type:   Sorted Set (GEO index, Redis stores as ZSET with geohash scores)
GEOADD drivers:active {lng} {lat} {driver_id}
TTL:    30 seconds per member — set via per-driver expiry with EXPIRE trick
```

Individual driver TTL: `SET driver_ttl:{driver_id} 1 EX 30`. A keyspace notification on expiry triggers marking the driver offline.

**Kafka — location event stream:**
```
Topic:    driver.location.events
Key:      driver_id  (ensures ordered delivery per driver)
Value:    { driver_id, lat, lng, timestamp, status }
Retention: 7 days
```

**PostgreSQL — location_history (append-only):**
```
driver_id    UUID NOT NULL
latitude     DOUBLE PRECISION
longitude    DOUBLE PRECISION
timestamp    TIMESTAMPTZ NOT NULL
trip_id      UUID  -- nullable, set when driver is on a trip
```
Partitioned by `DATE(timestamp)` — daily partitions. Indexed on `(driver_id, timestamp DESC)` for trip replay queries.

**PostgreSQL — places (static, GeoHash-indexed):**
```
place_id     UUID PRIMARY KEY
name         TEXT
latitude     DOUBLE PRECISION
longitude    DOUBLE PRECISION
geohash      CHAR(9)   -- precision 9 ≈ 5m accuracy
category     TEXT
INDEX (geohash text_pattern_ops)  ← prefix search: WHERE geohash LIKE 'u4pruyd%'
```

> **Interviewer:** Why store geohash as a column in PostgreSQL instead of using PostGIS?

**Candidate:** PostGIS ST_DWithin is powerful but requires a PostGIS extension and has higher query planning overhead. For simple radius search at L5 scope, GeoHash prefix matching is simpler: a 6-character geohash covers ~1.2 km × 0.6 km. For a 3 km radius, query the center cell plus its 8 neighbors — 9 prefix queries or one `IN (...)` clause with 9 prefixes. No extension needed, no spatial index setup. PostGIS is better for complex polygon intersections; for circle-radius search, GeoHash is sufficient and deployable on vanilla PostgreSQL.

---

### Phase 5: HLD + Deep Dive (20 min)

> **Interviewer:** Show me the full design.

**Candidate:**

```
  Driver App
    │  POST /drivers/{id}/location (every 4 seconds)
    ▼
  Location Update Service (stateless, 10 instances)
    │
    ├──► GEOADD drivers:active {lng} {lat} {driver_id}   [Redis GEO Cluster]
    │    SET driver_ttl:{driver_id} 1 EX 30
    │
    └──► Kafka producer: driver.location.events
              │
              ▼
        Kafka Consumer (Location History Writer)
              │
              ▼
        PostgreSQL: location_history (daily partitions)

  Redis GEO Cluster (3 shards)
    ├── Shard 1: drivers A–H
    ├── Shard 2: drivers I–P
    └── Shard 3: drivers Q–Z
    │
    │  Keyspace notification on driver_ttl:{driver_id} expiry
    ▼
  Presence Service
    │  Mark driver offline in PostgreSQL driver_status table
    ▼
  Dispatch Service (notified)

  Rider App
    │  GET /drivers/nearby?lat=X&lng=Y&radius_km=3
    ▼
  Search Service
    │
    ├──► GEORADIUSBYMEMBER drivers:active {lat} {lng} 3 km ASC COUNT 10  [Redis]
    │
    ├──► Enrich with driver metadata from PostgreSQL (batch by driver_ids)
    │
    └──► Response: top 10 drivers with distance
```

**Candidate:** Let me explain the two hard parts: driver TTL and GeoHash boundary bug.

**Driver TTL / offline detection.** Each driver update sets `SET driver_ttl:{driver_id} 1 EX 30`. This is a separate key (not the GEO member itself — Redis GEO ZSETs don't support per-member TTL). Redis keyspace notifications trigger when the key expires after 30 seconds without a refresh. The Presence Service subscribes to `__keyevent@0__:expired` events, extracts the driver_id suffix, and removes the GEO member: `ZREM drivers:active {driver_id}`. This ensures stale ghost drivers don't appear in search results.

**GeoHash boundary bug.** A GeoHash encodes coordinates into a cell. If a driver is at the edge of cell `u4pruyd`, querying only that cell misses drivers 10 meters away in adjacent cell `u4pruyf`. Fix: always query the center cell plus all 8 surrounding cells. Redis `GEORADIUSBYMEMBER` does this automatically — it's the whole point of the Redis GEO API. For PostgreSQL place search, explicitly compute the 9 neighboring GeoHash prefixes and pass them as `WHERE geohash IN (prefix1, prefix2, ..., prefix9)`.

> **Interviewer:** How do you handle a hot GeoHash cell — like Times Square with 500 drivers in a single cell?

**Candidate:** Redis GEORADIUSBYMEMBER doesn't care about density — it returns all members within the radius regardless of how many are packed into one geographic area. The response for Times Square returns 500 drivers, but the query is still O(N + log M) where N is the result count and M is total members in the ZSET. We cap the result with `COUNT 10` to avoid sending 500 driver records to the rider app. The application-level concern is that 500 `GEOADD` calls per second hit the same ZSET — but since Redis processes these serially on one core, and each is O(log M), at M=250,000 that's log2(250,000) ≈ 18 operations. At 500 writes/sec to Times Square + 62K writes/sec total, the node is still well under capacity. No sharding needed within a city.

> **Interviewer:** Walk me through a full ride request — from rider opens app to dispatch.

**Candidate:** 
1. Rider opens app → `GET /drivers/nearby` → Search Service → `GEORADIUSBYMEMBER` → returns 10 nearest driver IDs with distance.
2. Rider selects ride type → `POST /rides` → Dispatch Service creates ride record in PostgreSQL with `status=searching`.
3. Dispatch Service runs the assignment algorithm: re-queries `GEORADIUSBYMEMBER` for freshest data, filters by vehicle_type and availability, picks closest available driver.
4. Dispatch Service sends push notification to driver via FCM/APNs through the Notification Service.
5. Driver accepts → Dispatch Service updates `rides.status=en_route`, marks driver as unavailable in PostgreSQL `driver_status`.
6. Driver's `GEOADD` updates continue flowing into Redis — rider's app polls `GET /rides/{ride_id}/driver-location` every 3 seconds, which queries Redis GEO for that specific driver_id's current position.

> **Interviewer:** How do you rate-limit driver location updates?

**Candidate:** Two layers. Server side: the Location Update Service checks `INCR rate:{driver_id} EX 3`. If the counter exceeds 1 within 3 seconds, return 429. This enforces max 1 update per 3 seconds. Client side: the driver app throttles at 4-second intervals using a local timer. The server-side rate limit is the safety net for misbehaving or buggy app versions.

---

### Common Cross-Questions and Strong Answers

*(Cross-question: Redis GEO vs PostGIS)*
> **Interviewer:** When would you switch from Redis GEO to PostGIS for driver search?

**Candidate:** When you need queries beyond simple radius circles: polygon geofences (is this driver in a restricted zone?), complex routing corridors, or multi-attribute spatial joins. PostGIS ST_Within, ST_Intersects, and ST_DWithin handle arbitrary geometries. Redis GEO is purely circle-radius with optional sorting. At 62K writes/sec and 100K reads/sec, Redis is the only realistic choice for the hot path. PostGIS could be a secondary system for geofence enforcement running on the historical track data, which is write-once and not latency-sensitive.

*(Cross-question: location precision)*
> **Interviewer:** DOUBLE PRECISION for lat/lng — is that overkill?

**Candidate:** No. DOUBLE PRECISION is 8 bytes with 15-16 significant digits. At the equator, 1 degree latitude = 111 km. With 15 significant digits you can represent positions to sub-nanometer accuracy. FLOAT (4 bytes, 7 digits) gives ~1 meter precision at equator — sufficient for routing but borderline for dense urban dispatch. DOUBLE is the safe choice and the storage cost difference (8 bytes vs 4 bytes per coordinate) is negligible. Redis GEO uses 52-bit geohash internally, giving ~0.6 meter precision — consistent with DOUBLE in PostgreSQL.

*(Cross-question: location history partitioning)*
> **Interviewer:** Why partition `location_history` by date instead of by driver_id?

**Candidate:** Access patterns drive partitioning. The primary query on `location_history` is trip replay: `WHERE driver_id = ? AND timestamp BETWEEN trip_start AND trip_end`. Trips last 20-40 minutes, always within one or two calendar days. Date partitioning means trip replay queries scan at most 2 partitions — each day's partition is ~170 GB, and PostgreSQL partition pruning skips all other partitions. Driver-ID hash partitioning would distribute writes evenly but force a full partition scan for any time-bounded query. Date partitioning also makes retention easy: `DROP PARTITION location_history_2026_01_01` to purge a day's data without table bloat.

*(Cross-question: driver clustering)*
> **Interviewer:** What if two drivers are at exactly the same GPS coordinates (at a taxi stand)?

**Candidate:** Redis GEO stores members by name (driver_id), not position. Two drivers at identical coordinates each have their own GEO entry — `GEOADD` with the same lat/lng but different member names creates two distinct entries. `GEORADIUSBYMEMBER` returns both. No collision, no overwrite. In PostgreSQL, the composite key is `(driver_id, timestamp)` so same-coordinate concurrent inserts are also safe.

*(Cross-question: multi-city sharding)*
> **Interviewer:** If we expand to 50 cities, how do you shard the Redis GEO structure?

**Candidate:** Shard by city: `drivers:active:{city_code}` — one ZSET per city. Search queries are always within a city boundary, so you never need cross-shard GEORADIUSBYMEMBER. Driver updates route to the correct shard by city_code in the driver profile. This is application-level sharding, not Redis Cluster hash sharding — you explicitly route to the right key. Redis Cluster can still be used for HA/replication within each city shard. For cities with 1M+ drivers (Mumbai, Jakarta), further shard by geohash prefix: `drivers:active:BOM:u4` etc.

---

<!-- END OF CHAPTER 74 -->
<!--
  Scope: L5 single-region. GeoHash-indexed PostgreSQL for places; Redis GEO Cluster for drivers.
  Key concepts:
    - GeoHash precision table (5 = 4.9km, 6 = 1.2km, 7 = 152m)
    - 9-cell neighbor query: center + 8 neighbors, always, to avoid boundary misses
    - Haversine filter: exact circle membership test after bounding-box DB query
    - Redis GEOADD / GEORADIUS / GEOSEARCH: spatial ZSET commands
    - Per-driver TTL: driver:ttl:{id} EX 30 + keyspace notification → ZREM
    - Redis Cluster geo-sharding: ~100K drivers/node at 50% utilization
    - Keyspace notification reliability: at-most-once; pair with a 60-second cleanup job
    - PostGIS vs GeoHash: PostGIS (GiST R-tree) is more accurate; GeoHash is simpler to explain
  Capacity:
    - 500M places: 100 GB raw PostgreSQL storage; 2 read replicas at 10M DAU
    - 1M drivers: 250K GEOADD/sec; Redis Cluster 4-10 primary nodes
    - Per-driver memory: ~90 bytes; 1M drivers = 90 MB total Redis memory (trivial)
    - Driver history: 2.16 TB/day via Kafka consumer → PostgreSQL partitioned table
  L5 interview target:
    - Design both subsystems, justify storage split in one sentence
    - Explain GeoHash from first principles (prefix = proximity)
    - State out-of-scope: routing, multi-region, ML ranking, traffic
    - Quantify driver write rate and justify Redis Cluster sizing
  Common mistakes:
    - Only designing place search (forgetting driver tracking)
    - Using PostgreSQL for driver updates (fails at 250K writes/sec)
    - Querying only the center GeoHash cell (boundary bug)
    - Not handling driver TTL (stale ghost drivers in dispatch)
    - Conflating distance sort with ETA sort (different systems)
    - Forgetting to rate-limit driver updates (1 update per 3 seconds max)
    - Treating keyspace notifications as reliable (they are at-most-once)
    - Not capping search radius (unbounded radius → millions of candidates)
    - Storing driver history in the Redis GEO ZSET (wrong tier — use Kafka → PostgreSQL)
    - Mixing up GEOADD argument order: GEOADD key lng lat member (not lat lng)
  Chapter written for: Google L5 / Senior SWE system design interview preparation.
  Pairs with Ch101 (Staff depth) and Ch63 (proximity theory) for a complete location picture.
-->
