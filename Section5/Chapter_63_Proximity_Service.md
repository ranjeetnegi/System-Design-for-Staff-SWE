# Chapter 61c: Proximity Service — Finding What Is Near You

> "Find coffee shops near me" sounds trivial. Behind it is a system that must
> answer radius queries on 200 million businesses, in under 100ms, for
> 100 million daily users — while the user's location changes with every step.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Proximity Service                          |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify (businesses only, or real-time objects?)    |
|  Min 2-9:   Users & use cases                                    |
|  Min 9-16:  Functional requirements                              |
|  Min 16-21: Scale math                                           |
|  Min 21-26: Non-functional requirements                          |
|  Min 26-29: Assumptions                                          |
|  Min 29-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                            |
|                                                                  |
|  Key numbers to know:                                            |
|  - Yelp: 200M businesses globally                                |
|  - Google Maps: 250M POIs (points of interest)                  |
|  - A typical "nearby" query: radius 500m to 50km               |
|  - GeoHash precision 6: 1.2km x 0.6km grid cell               |
|  - GeoHash precision 5: 4.9km x 4.9km grid cell               |
|  - Earth radius: 6,371 km                                        |
|  - 1 degree latitude = 111 km (constant)                        |
|  - 1 degree longitude = 111 km * cos(latitude)                  |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Static businesses with lat/lon                                |
|  - GeoHash-based indexing in Redis                               |
|  - Read-heavy, business data changes infrequently               |
|  - Single region, 100ms p99 search latency                      |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Real-time moving objects (drivers, users)                     |
|  - QuadTree with dynamic insertion/deletion at scale            |
|  - Multi-region with geo-routing                                 |
|  - Personalization layer on top of proximity results            |
|  - Handles "celebrity problem" (100M queries for                 |
|    businesses near Times Square)                                 |
+------------------------------------------------------------------+
```

---

## Phase 1: Users and Use Cases (Minutes 2-9)

### Who uses a proximity service?

Think of a proximity service like the yellow pages, but instead of being sorted by name, the pages are sorted by distance from wherever you are right now. The system's only job is to answer: "what is near me, right now, of type X?"

**Human users:**
- Mobile app users searching for nearby restaurants, coffee shops, gas stations, ATMs
- Delivery drivers looking for the nearest pickup point
- Travelers looking for hotels, tourist spots, or transit stops near their current location
- Emergency responders finding the nearest hospital, fire station, or defibrillator

**System users (L5 signal):**
- Mobile apps: issue search queries on behalf of users with user's GPS coordinates
- Recommendation engine: calls proximity service to get candidates, then ranks them by rating, price, user preference
- Ad targeting system: calls proximity service to find businesses near a user to show relevant ads
- Analytics pipeline: calls proximity service to compute business coverage density for market expansion decisions
- Delivery dispatch: calls proximity service to find the nearest available driver for an order

**Operational users:**
- Business owners: register their business (lat, lon, category, name)
- SRE: monitors query latency, cache hit rate, index freshness

### Core use cases

**P0 — Must have:**
- UC1: Given (user_lat, user_lon, radius_km, category), return all businesses within radius, sorted by distance
- UC2: Business owner can add a new business (or update location/details)
- UC3: Business owner can delete a business (permanently closed)

**P1 — Important:**
- UC4: Filter by business attributes (open now, minimum rating, price tier)
- UC5: Return business details (name, address, hours, rating, phone) along with distance

**Out of scope for L5:**
- Real-time location tracking of moving objects (drivers, users) — that is a separate system (Ch61h)
- Personalized ranking (showing businesses based on user history) — downstream of this service
- Map rendering — different system entirely
- Route planning / turn-by-turn — not proximity

### Edge cases with architecture implications

- **Dense urban area (Times Square)**: A 500m radius around Times Square contains 10,000+ businesses. Without a result limit, a query returns massive payloads. Forces: result limit (top 20 by distance), pagination.
- **Sparse rural area**: A 50km radius around a remote location contains 0-3 businesses. The system must handle gracefully (return empty set, suggest expanding radius).
- **Business at the exact edge of a radius**: Floating point precision for distance calculation must be consistent. A business 500.001m away should not appear in a 500m search.
- **Pole and date-line edge**: GeoHash behaves oddly near the poles and the 180th meridian (longitude wraps). Affects users in Alaska, Russia, New Zealand. Must be handled in neighbor cell calculation.
- **New business propagation**: A business added by an owner should appear in search results within 60 seconds (near-real-time index update).

### Alignment check

> "I am designing a proximity service for static businesses — think Yelp or Google Maps business search. The core operation is: given a user location and radius, return the nearest N businesses of a given category. I am not designing real-time location tracking for moving objects (drivers, users). The business database is relatively stable — businesses are added or updated occasionally, not continuously. Does that match your intent?"

---

## Phase 2: Functional Requirements (Minutes 9-16)

### Read flows

- **F1 — Nearby search**: `search(lat, lon, radius_km, category, limit) -> list of (business_id, distance)` sorted by distance ascending
- **F2 — Business detail**: `get_business(business_id) -> {name, lat, lon, category, address, phone, hours, rating}` — called after F1 to get full details for each result

### Write flows

- **F3 — Add business**: `add_business(name, lat, lon, category, address, phone, hours) -> business_id`
- **F4 — Update business**: `update_business(business_id, fields_to_update)` — update location, name, hours, etc.
- **F5 — Delete business**: `delete_business(business_id)` — mark as deleted, remove from search index

### Control flows (L5 signal)

- **F6 — Index update propagation**: When a business is added/updated/deleted, the geo-index (GeoHash) must be updated within 60 seconds
- **F7 — Cache invalidation**: When a business is deleted or its location changes, cached query results that included that business must be invalidated
- **F8 — Search result caching**: Cache popular search queries (e.g., "coffee shops near downtown NYC") for 60 seconds to reduce DB load

### Key principle

F1 (search) reads from the geo-index (GeoHash index, fast), not the main business database directly. F2 (get_business) reads from the business database or a cache. These are deliberately split so the geo-index can be optimized purely for spatial lookups.

---

## Phase 3: Scale and Capacity (Minutes 16-21)

### User scale

- DAU: 100 million users
- Businesses: 200 million globally
- Peak concurrent users: 10 million (10% of DAU at peak)

### Activity scale

```
Searches per day:
  100M DAU * 5 searches/user/day = 500M searches/day
  500M / 86,400 = 5,787 searches/sec (average)
  Peak factor: 3x (evening, weekends) = ~17,000 searches/sec

Business writes per day:
  200M businesses, ~0.1% updated per day = 200,000 updates/day
  200,000 / 86,400 = 2.3 updates/sec (extremely low write rate)
  Read/write ratio: 17,000 / 2 = ~8,000:1 (massively read-heavy)

Data size:
  Per business record:
    business_id: 8 bytes
    lat, lon: 8 bytes each = 16 bytes
    geohash (precision 6): 6 bytes
    name: ~50 bytes
    category: 4 bytes
    address: ~100 bytes
    phone: 15 bytes
    hours: 50 bytes
    rating: 4 bytes
    Total: ~260 bytes per business

  200M businesses * 260 bytes = 52 GB (fits in memory!)

GeoHash index size:
  200M entries * (geohash_6 bytes + business_id bytes) = 200M * 14 bytes = 2.8 GB
  (fits easily in Redis)

Result payload:
  Top 20 results * 200 bytes per result = 4 KB per search response
```

### Peak load analysis

```
At 17,000 searches/sec:
  Each search touches the GeoHash index (Redis lookup)
  Redis can handle 500K ops/sec per shard (single-threaded, but each op is fast)
  17,000 searches * 3 geohash cells per search (center + neighbors) = 51,000 Redis ops/sec
  -> 1 Redis shard handles this comfortably

  If we cache 10% of queries (popular queries near major cities):
  Effective load on index = 90% * 17,000 = 15,300 searches/sec -> still fine on 1 shard

  For 3x redundancy: 3 Redis replicas (1 primary, 2 read replicas)
```

### Design target

- Search latency: p50 = 20ms, p99 = 100ms
- Write (add/update business): eventual consistency acceptable, propagate to index within 60 seconds
- Sustained throughput: 6,000 searches/sec; peak: 20,000 searches/sec

---

## Phase 4: Non-Functional Requirements (Minutes 21-26)

### Latency targets

- Nearby search (F1): p50 = 20ms, p99 = 100ms (Redis lookup + distance calculation + sort)
- Business detail (F2): p50 = 5ms, p99 = 20ms (from cache)
- Business write (F3-F5): eventual consistency; index updates within 60 seconds

### Availability

- Read path: 99.99% (4 nines — this is a user-facing search, outage = users see broken maps)
- Write path: 99.9% (brief write outage acceptable — business rarely updated)

### Consistency model

- **Search results**: eventual consistency for geo-index. A newly added business may take up to 60 seconds to appear in results. Acceptable — business listings are not financial transactions.
- **Business details**: strong consistency. If a business is deleted, it must not appear in detail lookups even if it briefly appears in search results (handle by checking existence in detail fetch).
- **Trade-off**: strong consistency on the geo-index would require distributed transactions (slow). Eventual consistency allows a simple async index update pipeline.

### Durability

- Business records (the source of truth): replicated 3 ways in Postgres with daily backups
- GeoHash index (derived): can be rebuilt from Postgres if lost. Not the source of truth.

### Trade-offs to state out loud

> "I am choosing GeoHash over QuadTree for the geo-index. GeoHash maps a 2D location to a 1D string that can be stored in Redis sorted sets or hash maps — very simple to implement. QuadTree gives better density adaptation (splits dense areas more finely) but is harder to implement correctly in a distributed setting. For static businesses, GeoHash's simplicity wins."

> "I am caching popular searches at the API layer for 60 seconds. The trade-off: a newly added business in a popular area may not appear in cached results for up to 60 seconds after the cache TTL. This is acceptable given that business writes are rare."

---

## Phase 5: Assumptions and Constraints (Minutes 26-29)

### Assumptions

- A1: Business locations are static (businesses do not move). Any location change is treated as an update.
- A2: The maximum radius for a search is 50km. Beyond 50km, the system returns "no results in range, try a broader search." This prevents queries that would return millions of results.
- A3: Result limit is 20 businesses per query page. Pagination supported via offset.
- A4: Category taxonomy is fixed (restaurant, coffee, hotel, gas_station, etc.) — not free-text.
- A5: All business data fits in memory (52 GB total) — we can use Redis for the geo-index.

### Constraints

- C1: Must return results within 100ms p99 — this requires an in-memory geo-index, not a disk-based spatial query.
- C2: Single region deployment (L5 scope).

### Simplifications

- S1: Distance is computed using the Haversine formula (correct great-circle distance). A simpler Euclidean approximation works for small radii (<10km) but breaks at large radii and near poles — we use Haversine everywhere for correctness.
- S2: The geo-index is rebuilt nightly from Postgres as a safety net, even though real-time updates keep it current.
- S3: "Open now" filtering is applied after the proximity search (post-filter), not during — simplifies the geo-index.

---

## Architecture Design — HLD (Minutes 29-42)

### Opening analogy

Imagine the world divided into a grid of squares, like a giant chessboard. Each square has a name — a short code that describes its location. If you want to find all coffee shops near you, you just look up all businesses in your square and the 8 squares surrounding it. You don't have to check every business in the world — just the ones in the local 9 squares.

That is GeoHash. Instead of searching the entire map, the system narrows the search to a small neighborhood of grid cells, then computes exact distances only for businesses within those cells.

### Full HLD ASCII diagram

```
[Mobile App] ---(search request: lat, lon, radius, category)---> [API Gateway]
                                                                       |
                                              +------------------------+
                                              |
                                              v
                                  +---------------------+
                                  |   LOCATION SERVICE  |
                                  |   (stateless API)   |
                                  |   10 instances      |
                                  +---------------------+
                                         |      |
                        +----------------+      +-----------------+
                        |                                         |
                        v                                         v
             +--------------------+                   +--------------------+
             |   GEO-INDEX        |                   |  BUSINESS DB CACHE |
             |   (Redis cluster)  |                   |  (Redis cache)     |
             |   GeoHash -> [IDs] |                   |  business_id ->    |
             |   2.8 GB RAM       |                   |  full details      |
             |   Stateful         |                   |  Stateful          |
             +--------------------+                   +--------------------+
                        |                                         |
                        | (cache miss: look up)                   | (cache miss)
                        v                                         v
             +--------------------+                   +--------------------+
             |  GEO-INDEX PRIMARY |                   |   BUSINESS DB      |
             |  (Redis primary)   |                   |   (Postgres)       |
             |  + 2 read replicas |                   |   200M rows        |
             |  Stateful          |                   |   52 GB on disk    |
             |                   |                   |   Source of truth  |
             +--------------------+                   +--------------------+
                        ^
                        | (index update)
                        |
             +--------------------+
             |  INDEX UPDATE      |
             |  WORKER            |
             |  (async consumer)  |
             |  Stateless         |
             +--------------------+
                        ^
                        |
             +--------------------+
             |  BUSINESS WRITE    |
             |  SERVICE           |
             |  (stateless API)   |
             +--------------------+
                        ^
                        |
             [Business Owner App] ---(add/update/delete business)
```

### Component responsibilities table

```
+----------------------+-------------------------------+-----------+------------------+
| Component            | Responsibility                | Stateful? | Scale target     |
+----------------------+-------------------------------+-----------+------------------+
| API Gateway          | Auth, rate limiting, routing  | NO        | 20K req/sec      |
+----------------------+-------------------------------+-----------+------------------+
| Location Service     | Translate search params to    | NO        | 10 instances     |
|                      | GeoHash cells, call index,    |           | 20K req/sec      |
|                      | compute exact distances,      |           |                  |
|                      | filter, sort, paginate        |           |                  |
+----------------------+-------------------------------+-----------+------------------+
| Geo-Index (Redis)    | GeoHash -> list of business   | YES       | 51K ops/sec      |
|                      | IDs within that cell          |           | 2.8 GB RAM       |
|                      |                               |           | 1P + 2 replicas  |
+----------------------+-------------------------------+-----------+------------------+
| Business DB Cache    | business_id -> full details   | YES       | 200K ops/sec     |
| (Redis)              | (name, hours, rating, etc.)   |           | ~10 GB RAM       |
|                      | TTL: 5 minutes                |           |                  |
+----------------------+-------------------------------+-----------+------------------+
| Business DB          | Authoritative business store  | YES       | 2 writes/sec     |
| (Postgres)           | 200M rows, sharded by         |           | 6K reads/sec     |
|                      | business_id                   |           |                  |
+----------------------+-------------------------------+-----------+------------------+
| Business Write Svc   | Validate, write to Postgres,  | NO        | 2 writes/sec     |
|                      | publish to Kafka for index    |           |                  |
+----------------------+-------------------------------+-----------+------------------+
| Index Update Worker  | Consume Kafka business events | NO        | 2 events/sec     |
|                      | Update GeoHash index in Redis |           |                  |
+----------------------+-------------------------------+-----------+------------------+
```

### Write path (adding a new business)

```
Step 1: Business owner submits add request
  [Business Owner App] -> POST /businesses {name, lat, lon, category, address, hours}
  [API Gateway] -> authenticates business owner, routes to Business Write Service

Step 2: Validate and persist
  [Business Write Service]:
  - Validate lat in [-90, 90], lon in [-180, 180]
  - Generate business_id (UUID)
  - Compute GeoHash for (lat, lon) at precision 6
  - INSERT INTO businesses (id, name, lat, lon, geohash, category, ...) -> Postgres
  - Publish event to Kafka: {event="business_added", business_id, geohash, category}
  - Return 201 Created with business_id

Step 3: Async index update (within 60 seconds)
  [Index Update Worker] consumes Kafka event:
  - event="business_added", business_id="abc", geohash="9q8yy", category="coffee"
  - Redis: SADD geo:coffee:9q8yy abc
  - (The geo-index key is "geo:{category}:{geohash}", value is a set of business IDs)
  - Also: HSET business:abc lat {lat} lon {lon} geohash {geohash}  (for distance calc)
```

```
[Business Owner] -> [Write Service] -> [Postgres (sync)] -> [Kafka event (async)]
                                                                     |
                                                                     v
                                                        [Index Worker] -> [Redis geo-index]
```

### Read path (search for nearby businesses)

```
Step 1: User searches
  [Mobile App] -> GET /businesses/nearby?lat=37.7749&lon=-122.4194&radius=1&category=coffee
  [API Gateway] -> routes to Location Service instance

Step 2: Translate location to GeoHash cells
  [Location Service]:
  - Convert (37.7749, -122.4194) to GeoHash precision 6 = "9q8yy6"
  - Determine which GeoHash cells overlap with the radius circle
  - For radius 1km at precision 6 (1.2km x 0.6km cells):
    Use the center cell + 8 surrounding neighbors = 9 cells total
  - cells = ["9q8yy6", "9q8yy7", "9q8yyd", "9q8yye", "9q8yy4",
             "9q8yy5", "9q8yyh", "9q8yyg", "9q8yys"]

Step 3: Fetch business IDs from Redis
  [Location Service] -> Redis:
  For each cell in cells:
    SMEMBERS geo:coffee:{cell}  -> list of business IDs in that cell
  Merge all results into one set of candidate business IDs

Step 4: Fetch lat/lon for candidates
  [Location Service] -> Redis:
  For each candidate business_id:
    HGET business:{id} lat, lon
  (These are lightweight -- just coordinates, not full details)

Step 5: Compute exact distance and filter
  [Location Service]:
  For each candidate:
    dist = haversine(user_lat, user_lon, biz_lat, biz_lon)
    if dist <= radius: keep
  Sort by dist ascending
  Take top 20

Step 6: Fetch full details for top 20
  [Location Service] -> Redis cache:
  For each of the 20 result business IDs:
    GET business_details:{id}  -> cache hit (5min TTL): return cached details
    cache miss: fetch from Postgres, cache it, return

Step 7: Return response
  Return: [{business_id, name, distance, category, address, rating}, ...]
```

```
[User] -> [Location Service]
               |
               v
       [GeoHash: center + 8 neighbors]
               |
               v
       [Redis: SMEMBERS for 9 cells] -> candidate IDs
               |
               v
       [Redis: HGET lat/lon per ID]
               |
               v
       [Haversine filter + sort]
               |
               v
       [Redis cache: full details for top 20]
               |
               v (cache miss)
       [Postgres: fetch and cache]
               |
               v
       [Return top 20 to user]
```

### Key design decisions

```
+------------------+----------------------------+------------------+--------------------+
| Decision         | Why chosen                 | Rejected         | Trade-off          |
+------------------+----------------------------+------------------+--------------------+
| GeoHash for      | Maps 2D (lat, lon) to 1D   | QuadTree         | GeoHash has fixed  |
| spatial index    | string storable in Redis   |                  | cell sizes --      |
|                  | Prefix matching gives       |                  | dense urban areas  |
|                  | neighbor cells. Simple     |                  | and sparse rural   |
|                  | to implement and operate.  |                  | get same cell size.|
|                  |                            |                  | QuadTree adapts    |
|                  |                            |                  | but is harder to   |
|                  |                            |                  | distribute.        |
+------------------+----------------------------+------------------+--------------------+
| Redis SADD for   | Set operations: add O(1),  | PostGIS          | PostGIS has true   |
| geo-index        | lookup O(1), delete O(1).  | spatial indexes  | spatial operators  |
|                  | 2.8 GB fits in Redis RAM.  |                  | but disk-based.    |
|                  | 51K ops/sec easy on Redis. |                  | At 100ms target,   |
|                  |                            |                  | in-memory wins.    |
+------------------+----------------------------+------------------+--------------------+
| 9 neighbor cells | A circle of radius R can   | Expanding radius | Expanding is more  |
| for radius search| overlap up to 9 GeoHash    | approach         | complex. 9-cell    |
|                  | cells of the precision     |                  | covers the common  |
|                  | matching R. 9 cells =      |                  | case well with a   |
|                  | 1 center + 8 neighbors.    |                  | false-positive     |
|                  |                            |                  | filter step.       |
+------------------+----------------------------+------------------+--------------------+
| Haversine for    | Correct at all distances   | Euclidean approx | Euclidean has up   |
| distance calc    | and latitudes. Essential   |                  | to 25% error near  |
|                  | near poles and for large   |                  | poles and for      |
|                  | radii (>10km).             |                  | radius > 20km.     |
|                  |                            |                  | Not acceptable.    |
+------------------+----------------------------+------------------+--------------------+
| Async index      | Business writes are rare   | Synchronous      | Eventual           |
| update via Kafka | (2/sec). Async decouples   | index update     | consistency: new   |
|                  | write performance from     |                  | business visible   |
|                  | index update. Kafka gives  |                  | after 60s, not     |
|                  | durability (no lost        |                  | immediately.       |
|                  | updates if worker crashes).|                  |                    |
+------------------+----------------------------+------------------+--------------------+
```

---

## Component-Level Design: Deep Dives

### Component 1: GeoHash Index in Redis

**Analogy:** Imagine dividing a world map into a grid of squares, and giving each square a short nickname. The square covering downtown San Francisco might be called "9q8yy6". All businesses inside that square are listed under "9q8yy6". To find nearby coffee shops: look up "9q8yy6" and its 8 neighbors. Much faster than checking all 200 million businesses.

**GeoHash structure:**

```
Redis key:   geo:{category}:{geohash_precision_6}
Redis type:  Set (SADD, SMEMBERS, SREM)
Redis value: Set of business_ids

Example:
  geo:coffee:9q8yy6 -> {biz_001, biz_002, biz_005, biz_017}
  geo:coffee:9q8yy7 -> {biz_003, biz_009}
  geo:restaurant:9q8yy6 -> {biz_020, biz_021, biz_022}

Also:
Redis key:   business:{business_id}
Redis type:  Hash (HSET, HGET)
Redis value: lat, lon, geohash (for fast distance calculation without hitting Postgres)

Example:
  business:biz_001 -> {lat: 37.7749, lon: -122.4194, geohash: 9q8yy6}
```

**Memory estimate:**

```
GeoHash index:
  Key: "geo:coffee:9q8yy6" = ~20 bytes
  Set: average 10 businesses per cell * 36 bytes (UUID) = 360 bytes per cell
  Number of cells with businesses: 200M businesses / 10 per cell = 20M cells
  Total: 20M * (20 + 360) bytes = 7.6 GB for all categories

Business hash:
  200M businesses * (8 + 8 + 6) bytes = 200M * 22 = 4.4 GB

Total Redis: ~12 GB -> fits on a single 32 GB Redis instance
             Use 3 shards for distribution and availability
```

**Pseudocode for search:**

```
function search_nearby(user_lat, user_lon, radius_km, category, limit):
    precision = geohash_precision_for_radius(radius_km)
    center_hash = encode_geohash(user_lat, user_lon, precision)
    neighbor_hashes = get_neighbors(center_hash)  // 8 surrounding cells
    all_cells = [center_hash] + neighbor_hashes

    candidate_ids = set()
    for cell in all_cells:
        key = "geo:" + category + ":" + cell
        ids = redis.smembers(key)
        candidate_ids.update(ids)

    results = []
    for biz_id in candidate_ids:
        coords = redis.hget("business:" + biz_id, ["lat", "lon"])
        dist = haversine(user_lat, user_lon, coords.lat, coords.lon)
        if dist <= radius_km:
            results.append((biz_id, dist))

    results.sort(by=dist)
    return results[:limit]
```

**GeoHash precision selection by radius:**

```
+----------------+-------------------+------------------+
| Search radius  | GeoHash precision | Cell size        |
+----------------+-------------------+------------------+
| <= 1 km        | 6                 | 1.2km x 0.6km    |
| 1 - 5 km       | 5                 | 4.9km x 4.9km    |
| 5 - 50 km      | 4                 | 39km x 20km      |
+----------------+-------------------+------------------+

Rule: pick precision such that each cell is smaller than the radius.
Then 9 cells (3x3 grid) always covers the search circle.
```

**Failure mode:** If a Redis primary fails, reads automatically fail over to a replica (read replica promotes to primary via Redis Sentinel or Cluster). The index is eventually consistent, so a replica may be up to 1 second behind the primary — during failover, a newly added business in the last 1 second may briefly not appear. This is acceptable.

---

### Component 2: GeoHash Algorithm (how it works)

**Analogy:** GeoHash is like a postal code system for the entire planet. Just like a ZIP code narrows down to a city, and a ZIP+4 narrows to a block, GeoHash precision 1 is a continent-sized area and GeoHash precision 9 is the size of a room.

**Encoding algorithm:**

```
Encode (lat=37.7749, lon=-122.4194) to GeoHash precision 6

Step 1: Interleave bits of longitude and latitude
  Start with: lon range [-180, 180], lat range [-90, 90]

  For longitude (-122.4194):
  Bit 1: -122.4194 > 0? No  -> bit=0, range -> [-180, 0]
  Bit 2: -122.4194 > -90?  Yes -> bit=1, range -> [-90, 0]
  Bit 3: -122.4194 > -45?  No  -> bit=0, range -> [-90, -45]
  ...continue until 30 bits total for precision 6

  Interleaved bits: longitude bit, latitude bit, longitude bit, ...

Step 2: Group into 5-bit chunks
  30 bits -> 6 chunks of 5 bits each

Step 3: Encode each 5-bit chunk to base-32 alphabet
  Base-32 alphabet: "0123456789bcdefghjkmnpqrstuvwxyz"
  (letters i, l, o excluded to avoid confusion with numbers 1, 0)

Result: "9q8yy6"
```

**Neighbor calculation:**

```
GeoHash neighbors share a prefix in the geohash alphabet.
"9q8yy6" neighbors:
  N:  "9q8yy7"   S:  "9q8yy4"   E:  "9q8yyd"   W:  "9q8yyh"
  NE: "9q8yye"   NW: "9q8yy5"   SE: "9q8yys"   SW: "9q8yyg"

This neighbor lookup is O(1) - computed from character lookup tables.
No tree traversal. Pure string manipulation using the base-32 adjacency table.
```

**The "edge" problem:**

Two GeoHash cells that are physically adjacent can have very different strings if they are on opposite sides of a GeoHash boundary (e.g., near longitude 0 or the 180-degree date line). The neighbor lookup algorithm correctly handles this via a lookup table, not by simple string arithmetic.

---

### Component 3: Haversine Distance Calculation

**Analogy:** The Earth is a sphere. If you draw a straight line between two points on a globe, it goes through the Earth. The real distance between two cities is the arc along the Earth's surface. Haversine computes this arc distance correctly.

**Why Euclidean is wrong:**

```
At 50km radius near latitude 60 degrees (Oslo):
  1 degree longitude = 111 * cos(60) = 55.5 km (not 111 km)
  Euclidean treats both degrees as equal -> error grows at high latitudes

Error at 50km radius near latitude 60 degrees: up to 25%
A business 45km away could appear as 37km (inside radius) or 53km (outside radius).
This is not acceptable.
```

**Haversine formula:**

```
function haversine(lat1, lon1, lat2, lon2) -> km:
    R = 6371  // Earth radius in km
    d_lat = to_radians(lat2 - lat1)
    d_lon = to_radians(lon2 - lon1)
    a = sin(d_lat/2)^2
      + cos(to_radians(lat1)) * cos(to_radians(lat2)) * sin(d_lon/2)^2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c
```

**Performance:** Each Haversine call: ~100 nanoseconds. For 1,000 candidates: 0.1ms. Negligible vs 100ms target.

---

### Component 4: Business Write Service and Index Update Pipeline

**Analogy:** Think of a library catalog. When a new book arrives, the librarian first enters it into the main catalog (Postgres). Then a separate team updates the physical shelf index (Redis geo-index) a short while later. The catalog is always authoritative; the shelf index catches up asynchronously.

**Write path with Kafka:**

```
[Business Write Service]
    1. Validate input (lat/lon range, category, required fields)
    2. Generate business_id = UUID4
    3. Compute geohash = encode_geohash(lat, lon, precision=6)
    4. Write to Postgres (synchronous, transactional)
    5. Publish to Kafka topic "business-events":
       {event_type="ADDED", business_id, geohash, category, lat, lon}
    6. Return 201 Created

[Index Update Worker] (async, within 60 seconds)
    For ADDED:
      redis.sadd("geo:" + category + ":" + geohash, business_id)
      redis.hset("business:" + business_id, {lat, lon, geohash})

    For UPDATED (location changed):
      old_geohash = redis.hget("business:" + business_id, "geohash")
      if old_geohash != new_geohash:
        redis.srem("geo:" + category + ":" + old_geohash, business_id)
        redis.sadd("geo:" + category + ":" + new_geohash, business_id)
      redis.hset("business:" + business_id, {lat, lon, geohash})

    For DELETED:
      geohash = redis.hget("business:" + business_id, "geohash")
      redis.srem("geo:" + category + ":" + geohash, business_id)
      redis.del("business:" + business_id)

    Commit Kafka offset after successful Redis update
```

**Why Kafka between write service and index worker?**

If Redis is slow or down, the write service does not block. Kafka acts as a durable buffer. The index update worker replays from Kafka when Redis recovers. No events are lost.

---

### Component 5: Search Result Caching

**Analogy:** Thousands of users in Manhattan search for "coffee shops near Times Square" every minute. Without caching, each search independently hits Redis. With caching, the first search stores the result for 60 seconds. The next 10,000 identical searches return the cached result instantly.

**Cache key design:**

```
Key: search_cache:{category}:{geohash_precision4}:{radius_bucket}
     (rounded to precision 4 = ~40km cell, not exact lat/lon)
     (radius bucketed: 0-1km, 1-5km, 5-20km, 20-50km)

Value: JSON list of {business_id, distance}
TTL: 60 seconds

Why precision 4 (not 6)?
  Precision 6 = 1.2km cell -> too fine, few cache hits
  Precision 4 = 39km cell -> users within 39km of each other share cache
  "Coffee near downtown SF" is the same for anyone within a few km of downtown.

Cache hit rate estimate:
  Top 1% of locations (major cities) account for 50% of queries
  Hit rate for top 1% locations: ~80%
  Overall hit rate: 50% * 80% = 40%
  Effective Redis geo-index load: 60% of 17,000 = 10,200 searches/sec -> fine
```

---

## Deep Concept Explanations (SSE Cross-Questioning Targets)

### Concept 1: GeoHash vs QuadTree vs R-tree

An interviewer will probe: "Why GeoHash over QuadTree? What does QuadTree do that GeoHash cannot?"

**GeoHash:**

```
- Fixed grid: precision 6 = 1.2km x 0.6km everywhere
- Dense city (10,000 businesses/km^2) and sparse desert (0.01/km^2) get same cell size
- Advantage: O(1) lookup, simple string ops, easy to store in Redis
- Disadvantage: fixed cell size wastes space in sparse areas, too coarse in dense areas
```

**QuadTree:**

```
- Recursively divides map into 4 quadrants
- Splits a quadrant when it exceeds threshold businesses (e.g., 100)
- Dense areas: many subdivisions -> fine resolution
- Sparse areas: few subdivisions -> coarse resolution

World -> [NW][NE][SW][SE]
NW (North America) -> [NW][NE][SW][SE]
NW-NE (rural Canada, 3 businesses) -> leaf node
NW-SW (NYC metro, dense) -> [NW][NE][SW][SE] -> ... many more subdivisions
```

**R-tree:**

```
- Minimum bounding rectangles: each node covers a spatial region
- Used in PostGIS, SQLite spatial extension
- Excellent for polygon search, arbitrary spatial queries
- Disk-based -> latency higher than in-memory Redis
- Best when: complex spatial queries, data doesn't fit in RAM
```

**Summary:**

```
+------------+------------------+------------------+------------------+
| Index type | Density adaptive | In-memory easy?  | Complexity       |
+------------+------------------+------------------+------------------+
| GeoHash    | No (fixed grid)  | Yes (Redis)      | Simple           |
| QuadTree   | Yes              | Harder (custom)  | Moderate         |
| R-tree     | Yes              | No (disk-based)  | Use a library    |
+------------+------------------+------------------+------------------+

L5: GeoHash. Simple, correct, in-memory.
L6: QuadTree for real-time moving objects where density varies wildly.
```

---

### Concept 2: The 9-Cell Problem

An interviewer will probe: "Is 9 cells always sufficient? What can go wrong?"

**When 9 cells work:**

```
Rule: if radius R < cell_width, the circle fits in a 3x3 grid.
  Precision 6 cell width = 1.2km
  Radius 1km < 1.2km -> 9 cells always covers the circle. Safe.

  Precision 5 cell width = 4.9km
  Radius 3km < 4.9km -> 9 cells always covers. Safe.
```

**When 9 cells fail:**

```
Case 1: Radius larger than cell
  Radius 5km at precision 6 (cell = 1.2km)
  5km circle needs 5/1.2 = 4+ cells in each direction -> 5x5 = 25 cells minimum
  With only 9 cells, businesses at the outer ring are missed.

  Fix: use lower precision. At precision 4 (cell = 39km), radius 5km < 39km -> 9 cells work.

Case 2: Date line (lon = 180 / -180)
  User at lon = 179.9 (eastern Russia): GeoHash prefix "xz..."
  Business at lon = -179.9 (same physical area): GeoHash prefix "b0..."
  These are completely different prefixes. Neighbor algorithm does not bridge them.

  Fix: if abs(user_lon) > 170, run two searches: one normal, one with lon +/- 360.

Case 3: Near the poles (lat > 85 degrees)
  GeoHash cells near poles are extremely narrow in longitude
  A 1km circle may span hundreds of GeoHash cells at precision 6
  Fix: use precision 3 or 4 for users above lat 85 degrees
```

---

### Concept 3: Haversine vs Euclidean vs Vincenty

**Three formulas:**

```
1. Euclidean:
   dist = sqrt((lat2-lat1)^2 + (lon2-lon1)^2) * 111 km/degree
   Error: up to 25% at large radii, high latitudes
   Speed: fastest (2 multiplications + sqrt)
   Use case: prototype only, < 10km at mid-latitudes

2. Haversine (what we use):
   Assumes Earth is a perfect sphere
   Accurate to 0.3% for all distances
   Speed: 6 trig ops + atan2 (~100ns)
   Use case: production proximity service (our choice)

3. Vincenty:
   Assumes Earth is oblate spheroid (flattened at poles)
   Accurate to 0.5mm (sub-millimeter)
   Speed: 10-50x slower than Haversine (iterative)
   Use case: aviation, GPS, surveying
   Overkill for "find coffee shops"
```

**Practical note:** Redis has a native `GEOSEARCH` command that uses Haversine internally. If you use Redis native geo commands, you get Haversine for free. However, Redis native geo commands have limitations for sharding by category, which is why our design uses custom Redis Sets.

---

### Concept 4: Candidate Expansion Pattern

An interviewer will probe: "You return 20 results. What if there are 10,000 in the radius? What if 0?"

**The pattern:**

```
Phase 1: Broad filter (cheap, approximate)
  Fetch all business IDs from the 9 GeoHash cells
  Over-fetches: some IDs are in the cell but outside the radius circle
  (GeoHash cells are rectangles; radius query is a circle)
  Over-fetch ratio: typically 20-40% of candidates are outside exact radius

Phase 2: Exact filter (Haversine)
  Compute exact distance for each candidate
  Filter: keep dist <= radius
  Sort ascending
  Return top 20
```

**Dense area (Times Square, 10,000 businesses in 1km):**

```
9 cells contain 10,000 business IDs
Haversine for 10,000: 1ms
Sort: 1ms
Total extra: 2ms -- not a problem for 100ms target

BUT: result limit is 20. Return top 20 nearest only.
If user wants more: pagination with offset.

Hard cap on candidates: if SMEMBERS returns > 5,000 IDs per cell,
cap at 5,000 (total 45,000 candidates across 9 cells).
Alert SRE if any cell exceeds 5,000 members.
```

**Sparse area (rural Alaska, 0 businesses in 50km):**

```
All 9 cells return empty sets.
Response: {results: [], message: "No businesses within 50km"}

Optional: tiered radius expansion
  if results empty at R:
    try 2R, then 50km (max)
    return {results, actual_radius_used}
```

---

### Concept 5: Database Choice for Business Records

An interviewer will probe: "Why Postgres? Why not Cassandra or DynamoDB?"

```
Business records characteristics:
  - Stable schema: name, lat, lon, category, address, hours, rating
  - 52 GB total (fits on one Postgres instance)
  - Very low write rate: 2/sec
  - Reads: 6,000/sec for detail lookups, but mostly served from cache
  - Strong consistency needed on delete: deleted business must not be accessible

Why Postgres wins:
  - Simple, well-understood, ACID
  - Detail lookup is a point query by business_id (PK) -> O(log n), fast
  - Cache absorbs 95%+ of reads -> Postgres sees ~300 reads/sec (trivial)

Why not Cassandra:
  - Eventual consistency by default -> deleted business might briefly appear
  - QUORUM reads are slower than Postgres at this scale
  - Overkill for 52 GB, low-write dataset

Why not DynamoDB:
  - Works, but: higher latency than Postgres+cache for point lookups
  - Higher cost at sustained 6,000 reads/sec
  - No complex queries needed, so DynamoDB's document model adds no value

Sharding strategy: shard by business_id (not geohash).
  Detail lookups (F2) are by business_id, not by location.
  The geo-index does spatial filtering and returns business_ids.
  Postgres only does point lookups by PK.
  At 10x scale (2B businesses): hash shard by business_id % 8 -> 8 instances.
```

---

## Failure Scenarios and Degradation

### Failure 1: Redis geo-index goes down

```
What happens:
  All nearby search queries fail (geo-index unavailable)

Degraded mode A: Postgres fallback
  Run: SELECT business_id, lat, lon FROM businesses
       WHERE category=? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
  (bounding box, then Haversine filter in app code)
  Latency: 500ms-2s (acceptable for degraded mode)
  Postgres with index on (category, lat, lon) handles this

Degraded mode B: Return stale search cache (extend TTL to 5 minutes)
  For queries in cache: return stale results
  For new queries: return empty with "search temporarily limited" message

Recovery:
  Redis restarts, loads RDB snapshot (up to 1 minute old)
  Index Update Worker replays last 1 minute of Kafka events
  Full recovery: 2-5 minutes
```

### Failure 2: Kafka down (index update pipeline blocked)

```
What happens:
  Business writes succeed (Postgres always first)
  Index update events cannot be published to Kafka

Solution: Outbox pattern
  Business Write Service writes two rows in the same Postgres transaction:
    1. businesses table (the actual business record)
    2. business_events table (the outbox: event_type, business_id, geohash, created_at)

  When Kafka recovers: Index Worker polls business_events table, processes events,
  publishes to Kafka, marks events as processed.
  No events are lost. Postgres is durable.
```

### Failure 3: Location Service instances fail (partial)

```
Stateless service: load balancer detects health check failure, routes away.
Remaining instances absorb load.
At 17,000 searches/sec with 10 instances: each handles 1,700/sec.
If 3 fail: 7 instances each handle 2,428/sec. Manageable.
Autoscaling: new instances boot in ~2 minutes and absorb load.
No state to restore.
```

### Failure 4: Cache stampede on a hot search key

```
Scenario: 1 million users simultaneously search "coffee near Times Square"
  - The cache key for this query expires at T=0
  - All 1M users get a cache miss simultaneously
  - All 1M try to recompute and write the cache key
  - Redis geo-index: 1M * 9 SMEMBERS = 9M Redis ops in 1 second

Prevention: probabilistic early expiration
  When TTL < 10s (10% of 60s TTL remaining):
    With probability 10%: recompute and refresh cache now
  This means cache is refreshed ~6 seconds before expiry on average
  No stampede: one request refreshes while 99.9% serve from warm cache

Alternative: distributed lock (mutex)
  When cache miss: acquire a lock for this cache key
  If lock acquired: compute, write, release lock
  If lock not acquired: wait briefly, then read (the winner just computed it)
```

### Blast radius table

```
Component failure     | Blast radius                          | Recovery time
----------------------|---------------------------------------|---------------
Redis geo-index       | All searches degrade to slow fallback | 2-5 min
Redis business cache  | Detail lookups go to Postgres         | 1-2 min
Postgres DB           | Writes fail; reads from cache         | 5-30 min
Kafka cluster         | Index updates paused (outbox catches)  | 5-30 min
Location Svc (50%)    | Latency up, no errors                 | 2 min autoscale
Location Svc (100%)   | All searches fail                     | 2 min autoscale
Index Update Worker   | Index updates delayed (Kafka retains) | 1-2 min
```

---

## SSE-Level Brainstorming Questions (Concept-Focused)

### GeoHash concepts

1. GeoHash is a space-filling curve. What property makes nearby physical locations share similar GeoHash values (most of the time)?
2. At GeoHash precision 1 there are 32 cells. At precision 6 there are 32^6 cells. What is that number? Can you simplify it?
3. Two points are in adjacent GeoHash cells at precision 5 but in different cells at precision 4. What does this tell you about their physical distance?
4. A GeoHash precision-6 cell near the equator is 1.2km x 0.6km. Near latitude 70 degrees, which dimension changes and why?
5. Why does GeoHash exclude the letters i, l, and o from its base-32 alphabet?
6. Increasing GeoHash precision by 1 divides each cell into how many sub-cells?
7. Can two physically distant points (e.g., 10,000km apart) share the same GeoHash prefix? What does that mean for proximity search?

### QuadTree concepts

8. A QuadTree splits a region when it has more than 100 points. What is the maximum depth for Earth at 10-meter resolution?
9. Why is inserting a new point into a distributed QuadTree harder than inserting into a GeoHash Redis set?
10. QuadTree vs KD-tree for 2D spatial search: what is the key difference?
11. A QuadTree cell at depth D covers a 2D region. After splitting, what fraction of the original area does each child cover?

### Distance and geometry concepts

12. Haversine assumes Earth is a perfect sphere. The actual radius varies from 6,357km (poles) to 6,378km (equator). By how many km does this affect a 1,000km distance?
13. At latitude 45 degrees, one degree of longitude is 78.5km. At the equator it is 111km. Explain why.
14. For a radius search of 1km at latitude 45 degrees, what is the Euclidean error in km compared to Haversine?
15. What is a spherical cap, and why does a "circle" of constant distance on a sphere become a spherical cap?

### Redis and caching concepts

16. Redis SMEMBERS returns all set members. For a cell with 100,000 businesses, this is a 3.6 MB response. What are two alternatives to SMEMBERS that avoid this?
17. Redis native GEORADIUS (now GEOSEARCH) does geo-proximity search in one command. Why might you not use it for a system that needs to search by category?
18. A Redis Sorted Set can store members with a score. How would you redesign the geo-index using a ZSET, and what would the score represent?
19. What is the cache stampede problem? Name two mitigations beyond the ones in this chapter.

### Consistency and write pipeline concepts

20. A business is deleted at T=0. Postgres is updated at T=0. Redis geo-index is updated at T=60s. What does a search at T=30s return? How do you handle it cleanly?
21. A business moves from location A to location B. Describe the exact sequence of Redis operations needed (SREM and SADD) and the race condition that can occur if not done atomically.
22. What is the Outbox pattern? Why does it solve the "Postgres write + Kafka publish must be atomic" problem without distributed transactions?
23. If the Index Update Worker processes events out of order (due to Kafka partition re-assignment), what could go wrong? How do you design for idempotency?

### API design concepts

24. The search API takes lat/lon as floating-point numbers. What precision (decimal places) is needed for 1-meter accuracy? For 100-meter accuracy?
25. A user denies location permission on their mobile device. What fallback location does the API use? What are the options?
26. How would you add "open now" filtering to the search API? Should it be done in the geo-index layer or as a post-filter? What are the trade-offs?
27. The search returns business_id and distance. Should it also return the business lat/lon? What privacy considerations apply?

### Scaling concepts

28. The system is deployed in one US region. A user in Singapore searches for nearby businesses. What is the latency impact, and how do you fix it?
29. You need to add real-time business availability (food trucks that post their location every 30 seconds). What changes to the architecture are required?
30. Personalization: show previously-liked businesses ranked higher. Where does this fit in the architecture? What data is needed? (Hint: it must not slow down the geo-index lookup.)
31. At 100x current scale (1.7B searches/sec), what breaks first in the architecture? What would you change?

---

## Intern to Staff Progression

### Same problem: "Find all restaurants within 1km of the user"

### Intern level

```
SELECT * FROM businesses
WHERE category = 'restaurant'
AND sqrt(pow(lat - ?, 2) + pow(lon - ?, 2)) < 0.009
-- 0.009 degrees ~ 1km (rough approximation)

Problems:
  1. Full table scan on 200M rows -> 30-60 seconds
  2. Euclidean approximation is wrong (no cos(lat) correction)
  3. sqrt() prevents index usage
  4. Returns wrong results at high latitudes

Intern has the right idea but wrong execution.
```

### L4 level

```
CREATE INDEX ON businesses (lat, lon) WHERE category = 'restaurant';

SELECT business_id, lat, lon FROM businesses
WHERE category = 'restaurant'
AND lat BETWEEN ? - 0.009 AND ? + 0.009
AND lon BETWEEN ? - 0.012 AND ? + 0.012

-- Then Haversine filter in application code

Better: index reduces scan from 200M to ~100 candidates
Then Haversine on 100 candidates is fast

Problems:
  1. At 6,000 reads/sec, Postgres disk I/O is the bottleneck (handles ~500/sec)
  2. No caching: every query hits Postgres
  3. Index does not account for GeoHash cell boundaries

L4 correct algorithm, wrong storage layer (disk vs in-memory).
```

```
L4:
+--------+  SELECT WHERE lat BETWEEN  +-----------+
|  App   | -------------------------> | Postgres  |
|        |  AND lon BETWEEN           | (disk)    |
|        | <------------------------- | Index on  |
+--------+  100 candidates -> filter  | (lat,lon) |
```

### L5 level

```
1. GeoHash encode user location to precision 6
2. SMEMBERS for 9 cells from Redis geo-index
3. HGET lat/lon per candidate from Redis
4. Haversine filter + sort -> top 20
5. Fetch full details from Redis cache (fallback to Postgres)
6. Cache search result for 60 seconds

Handles 17,000 searches/sec with 3 Redis shards.
Correct Haversine distance. Proper 9-cell neighbor search.
Acknowledges eventual consistency trade-off on index updates.
```

```
L5:
+--------+  SMEMBERS geo:coffee:9q8yy6  +-------+
|  App   | ---------------------------> | Redis |
|        |  (9 cells in pipeline)       | Geo   |
|        | <--------------------------- | Index |
|        |  candidate IDs               +-------+
|        |
|        |  HGET business:{id}          +-------+
|        | ---------------------------> | Redis |
|        |  lat, lon                    | Hash  |
|        | <--------------------------- +-------+
|        |
|        |  Haversine filter + sort
|        |
|        |  GET search_cache:{key}      +-------+
|        | ---------------------------> | Redis |
|        |  cache hit: return           | Cache |
|        | <--------------------------- +-------+
+--------+
```

### L6 level

```
1. QuadTree with adaptive cell size: dense areas (Manhattan) get 50m cells;
   sparse areas (Montana) get 50km cells. No wasted computation in rural areas,
   no overloaded cells in cities.

2. Real-time capable: QuadTree cells updated in-place on business location change.
   No async pipeline (Kafka) for location updates: real-time requirement means
   index must reflect changes within 1 second, not 60 seconds.

3. Multi-region: geo-DNS routes San Francisco users to US-West. Tokyo users to
   Asia region. Each region has a full replica of the geo-index.

4. Adaptive radius expansion with budget: first try R=1km (fast). If <5 results,
   try R=3km. Stop when 20+ candidates found. This avoids over-searching in
   dense areas and under-searching in sparse ones.

5. Hot key detection and routing: if Times Square geo-cell is getting 100K
   searches/sec, route it to a dedicated Redis shard with 10x replication.
   Detected automatically via key access frequency monitoring.

L6 addresses structural limitations of the L5 design (fixed cell size,
single region, no hot key handling) with targeted solutions, not overengineering.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)             | L6 (Staff)                     |
+---------------------+----------------------------+--------------------------------+
| Spatial index       | GeoHash in Redis, fixed     | QuadTree with adaptive splits  |
|                     | precision by radius bucket  | or hybrid GeoHash + QuadTree   |
+---------------------+----------------------------+--------------------------------+
| Business data       | Static (write infrequent)   | Semi-real-time: food trucks,   |
|                     | async 60s index propagation | pop-ups with 1s update latency |
+---------------------+----------------------------+--------------------------------+
| Distance calc       | Haversine, correct          | Haversine + awareness of       |
|                     |                             | Vincenty trade-off, pole edges |
+---------------------+----------------------------+--------------------------------+
| Caching             | 60s TTL Redis cache for     | CDN edge cache (10s for mobile)|
|                     | search results              | + Redis (60s) + probabilistic  |
|                     |                             | early expiration               |
+---------------------+----------------------------+--------------------------------+
| Scale               | 17K searches/sec, 1 region  | 200K searches/sec, 5 regions   |
+---------------------+----------------------------+--------------------------------+
| Consistency         | Eventual, 60s lag           | Near-real-time, 5s lag, strong |
|                     | acknowledged                | delete guarantee               |
+---------------------+----------------------------+--------------------------------+
| Dense area          | Hard cap on candidates      | Adaptive cell splitting,       |
|                     | acknowledged as known issue | hot-key routing, dedicated     |
|                     |                             | shard for celebrity cells      |
+---------------------+----------------------------+--------------------------------+
| Sparse area         | Return empty, suggest       | Adaptive radius with budget:   |
|                     | expanding radius            | auto-expand until N results    |
|                     |                             | or max radius exhausted        |
+---------------------+----------------------------+--------------------------------+
| Date line / poles   | Knows the edge case exists  | Quantifies: abs(lon) > 170     |
|                     | and flags it                | triggers dual-search; lat > 85 |
|                     |                             | drops to precision 3           |
+---------------------+----------------------------+--------------------------------+
| Failure handling    | Redis down -> Postgres      | Circuit breaker per region,    |
|                     | bounding-box fallback       | graceful degradation with      |
|                     |                             | stale cache extended TTL       |
+---------------------+----------------------------+--------------------------------+
| Write pipeline      | Kafka + async index worker  | Outbox for atomicity, dual-    |
|                     | 60s lag accepted            | write reconciliation, audit    |
|                     |                             | trail for compliance           |
+---------------------+----------------------------+--------------------------------+
| Monitoring          | Search latency, Redis ops   | Per-region p99, cache hit rate |
|                     | error rates                 | per geo-cell, hot key alerts,  |
|                     |                             | index lag per region           |
+---------------------+----------------------------+--------------------------------+
| Trade-offs          | States trade-offs when asked| Quantifies: "60s lag means     |
|                     |                             | 0.0001% of searches return a   |
|                     |                             | deleted business; cost of      |
|                     |                             | strong consistency: 50ms/write"|
+---------------------+----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Yelp GeoSearch Meltdown — Unbounded Candidates (2015)

**Company:** Yelp  
**What happened:** Yelp's mobile app increased its default search radius from 5km to 25km. In Manhattan, a 25km radius search returned 50,000+ candidate businesses from the spatial index. Distance calculation and sort for 50,000 candidates on the API server took 2-3 seconds, pushing p99 search latency from 200ms to 4 seconds. 20% of mobile users experienced search timeouts. The incident lasted 6 hours before the radius was reverted.

**Root cause:** No candidate count cap. The spatial index returned all businesses in the radius without bound.

**ASCII diagram:**

```
5km radius (before):
  [Geo-index: 500 candidates] -> [Haversine 500] -> 5ms -> OK

25km radius (after, Manhattan):
  [Geo-index: 50,000 candidates] -> [Haversine 50,000] -> 2.5s
                                 -> [Sort 50,000]      -> 0.5s
                                 -> Total: 3s          -> TIMEOUT
```

**Fix:** Hard cap at 5,000 candidates. If a cell returns >5,000 members, truncate and alert SRE. Added per-search candidate count metric with alert threshold at 2,000.

**Staff lesson:** Any system returning a variable-sized result set from an index must have a hard upper bound. "The user asked for 25km" does not mean the server must process 50,000 results linearly.

---

### Incident 2: Foursquare GeoHash Boundary Bug (2013)

**Company:** Foursquare  
**What happened:** Users near the GeoHash precision-5 boundary at -90 degrees longitude reported that businesses on one side of the street appeared in search results but businesses on the other side (same physical distance) did not. The neighbor computation used simple string arithmetic on the base-32 alphabet rather than a proper adjacency lookup table.

**Root cause:** At GeoHash column boundaries, adjacent cells have completely different strings. Simple character arithmetic produces the wrong neighbor.

**ASCII diagram:**

```
User at lon = -89.99:
  Center cell: "6pb..."
  West neighbor computed by naive string decrement: "6p9..." (WRONG)
  Actual west neighbor across boundary:             "dnh..." (correct)

Businesses at lon = -90.01 (100m away) -> in "dnh..." prefix -> not found
```

**Fix:** Replace string-arithmetic neighbor computation with a lookup table validated against actual physical coordinates. Added regression tests: for each cardinal direction, verify that the computed neighbor's center is physically adjacent to the input cell's center.

**Staff lesson:** Never implement GeoHash neighbor lookup from first principles using character arithmetic. Use a library or a pre-validated lookup table.

---

### Incident 3: Google Maps Cache Stampede During COVID Vaccine Announcement (2020)

**Company:** Google  
**What happened:** When a vaccine allocation announcement was made for NYC, millions of users simultaneously searched for "pharmacies near me." All searches landed on the same GeoHash cells covering Manhattan. The search result cache TTL (60 seconds) expired simultaneously for thousands of cache entries. Every cache miss triggered an independent computation and a write to the same Redis key. The Redis shard for Manhattan pharmacy searches received 100,000 writes/second for 30 seconds.

**Root cause:** Cache stampede — synchronized expiry of popular cache keys during a traffic spike.

**Fix:** Probabilistic early expiration: when cache key has < 10% of its TTL remaining, 10% of requests refresh the cache proactively. Also: distributed lock per cache key to serialize the recompute.

**Staff lesson:** Cache stampede is predictable. Popular geo-cells near major population centers should use jittered TTLs and proactive refresh to prevent synchronized expiry.

---

### Incident 4: Uber GeoSurge Precision Mismatch (2016)

**Company:** Uber  
**What happened:** Surge pricing computes demand (rider requests) divided by supply (driver locations) per geo-cell. An engineer changed the demand aggregation from GeoHash precision 5 (4.9km cells) to precision 6 (1.2km cells) without changing supply aggregation. Demand was now measured in small cells (few requests each); supply remained in large cells (many drivers). The system saw demand cells with zero matched supply and computed 10x surge in neighborhoods that had plenty of drivers.

**Root cause:** Demand and supply indexed at different GeoHash precisions. The division was nonsensical across mismatched granularities.

**ASCII diagram:**

```
Before (both precision 5):
  Cell "9q8yy" demand=50 requests, supply=45 drivers -> surge=1.1x (normal)

After (demand precision 6, supply precision 5):
  Demand cell "9q8yy6": 3 requests (small cell)
  Supply cell "9q8yy":  45 drivers (large cell, mismatched)
  Surge system: demand cell "9q8yy6" has 0 matched supply -> fallback = 10x surge
```

**Fix:** Single canonical GeoHash precision constant shared across all services. Cross-service contract validation in CI: any service consuming geo-cells must declare and validate its expected precision.

**Staff lesson:** Spatial precision is a system-wide contract. When two services independently compute over geographic data and combine the results, they must agree on granularity. Encode it as a shared versioned constant.

---

### Incident 5: Snap Map Redis Key Size Exhaustion (2019)

**Company:** Snapchat  
**What happened:** Snap Map stored all 50 million active user locations in a single Redis Sorted Set using Redis native GEOADD. At 50M entries * 100 bytes = 5 GB, the key lived on one Redis node. GEORADIUS operations on a 5 GB key caused latency spikes during memory allocation. During a traffic spike the Redis node ran out of memory. Snap Map went dark for 2.5 hours.

**Root cause:** All user locations in a single Redis key. Single keys cannot be distributed across Redis shards. One node held all 5 GB.

**Fix:** Shard by GeoHash prefix: one key per precision-3 region (~19 keys for North America). Each key: 5 GB / 19 = 260 MB — manageable per shard. Each key lives on a different Redis shard — geographic distribution = load distribution.

**Staff lesson:** A Redis key cannot be sharded. Any dataset that may grow large must be designed with key-level sharding from day one. "We'll shard when needed" means "we will have an outage when needed."

---

## Exercises

### Exercise 1: GeoHash cell count

**Problem:** At GeoHash precision 5 (cell = 4.9km x 4.9km), a user is at the center of a cell and searches 3km radius. How many cells do you need to guarantee all businesses within 3km are found?

**Solution:**

```
Radius R = 3km. Cell size = 4.9km.

Since R < cell_size (3 < 4.9), a 3x3 grid (9 cells) is sufficient.
The circle of diameter 6km fits inside the 3x3 grid of 4.9km cells (total 14.7km x 14.7km).

Even in the worst case (user at cell corner):
  Circle extends 3km in all directions from the corner.
  The 3x3 grid centered on the corner cell still covers all 4 quadrants of the circle.

Answer: 9 cells (center + 8 neighbors) is sufficient.

If R >= cell_size (e.g., R = 6km at precision 5):
  6km > 4.9km -> 9 cells may miss businesses in the outer ring.
  Switch to precision 4 (cell = 39km) and use 9 cells at that precision.
```

---

### Exercise 2: Redis memory sizing

**Problem:** You have 50M businesses, 3 categories average per business, average 5 businesses per GeoHash-6 cell. Estimate total Redis memory for the geo-index.

**Solution:**

```
Total business-category pairs: 50M * 3 = 150M entries

Redis Set memory per member:
  Member (UUID as string): 36 bytes
  Redis Set element overhead: ~50 bytes
  Per member: ~86 bytes
  150M members * 86 = 12.9 GB

Redis key overhead:
  50M businesses / 5 per cell = 10M cells * 3 categories = 30M keys
  Key string "geo:restaurant:9q8yy6" = ~22 bytes
  Redis key struct overhead: ~64 bytes
  30M * 86 = 2.6 GB

Business lat/lon hash:
  50M businesses * ~116 bytes = 5.8 GB

Total: 12.9 + 2.6 + 5.8 = ~21 GB
Recommend: 3 Redis shards of 16 GB each (48 GB capacity).
```

---

### Exercise 3: Haversine calculation

**Problem:** User is at (lat=37.7749, lon=-122.4194). A business is at (lat=37.7849, lon=-122.4094). Using the Haversine formula, estimate the distance in km (you can use approximate values for sin/cos).

**Solution:**

```
d_lat = to_radians(37.7849 - 37.7749) = to_radians(0.01) = 0.000175 rad
d_lon = to_radians(-122.4094 - (-122.4194)) = to_radians(0.01) = 0.000175 rad

a = sin(d_lat/2)^2 + cos(lat1_rad) * cos(lat2_rad) * sin(d_lon/2)^2

sin(d_lat/2) = sin(0.0000875) ≈ 0.0000875 (for small angles, sin(x) ≈ x)
sin(d_lat/2)^2 ≈ 7.66e-9

cos(37.7749 degrees) = cos(0.6594 rad) ≈ 0.791
cos(37.7849 degrees) ≈ 0.791 (nearly identical)

sin(d_lon/2) = sin(0.0000875) ≈ 0.0000875
sin(d_lon/2)^2 ≈ 7.66e-9

a = 7.66e-9 + 0.791 * 0.791 * 7.66e-9
  = 7.66e-9 + 0.625 * 7.66e-9
  = 7.66e-9 * 1.625
  = 1.245e-8

c = 2 * atan2(sqrt(1.245e-8), sqrt(1 - 1.245e-8))
  ≈ 2 * sqrt(1.245e-8)  (for small a, atan2(sqrt(a), 1) ≈ sqrt(a))
  = 2 * 0.0001116
  = 0.0002232 radians

dist = 6371 * 0.0002232 = 1.42 km

Answer: approximately 1.4 km. (Actual: 1.39 km via calculator.)
```

---

### Exercise 4: Cache invalidation on business deletion

**Problem:** Business "biz_001" (category=coffee, geohash="9q8yy6") is deleted at T=0. Describe the exact sequence of operations to ensure it does not appear in search results. What is the maximum time it remains visible?

**Solution:**

```
T=0: Delete request arrives

Step 1: Write Service marks as deleted in Postgres (synchronous)
  UPDATE businesses SET deleted_at = NOW() WHERE business_id = 'biz_001'

Step 2: Write event to Outbox table (same transaction)
  INSERT INTO business_events (type, business_id, geohash, category)
  VALUES ('DELETED', 'biz_001', '9q8yy6', 'coffee')

Step 3: Return 200 OK

T=0 to T~5s: Index Worker processes event (Kafka consumer, usually <5s)
  redis.srem("geo:coffee:9q8yy6", "biz_001")
  redis.del("business:biz_001")
  redis.del("business_details:biz_001")
  Invalidate search cache keys for this geohash:
    DEL "search_cache:coffee:9q8y:*"  (all precision-4 keys covering this cell)

After T~5s: geo-index no longer contains biz_001 -> not returned in new searches

For cached search results already computed before T=0:
  Those results are in cache with up to 60s TTL
  If they included biz_001: will be returned until TTL expires
  Maximum stale time for cached results: 60 seconds

Guard at detail fetch level:
  When rendering a search result, call GET /businesses/biz_001
  If deleted_at IS NOT NULL: return 404
  Client removes this result from the displayed list
  This catches stale cache results within one API call

Maximum visibility time:
  If index is updated within 5s: 5 seconds for new searches
  For cached search results: up to 60 seconds (TTL)
  With the detail-fetch guard: 0 seconds visible to the user
  (404 on detail fetch forces the UI to hide the result)
```

---

### Exercise 5: GeoHash precision selection

**Problem:** A user searches with radius 20km. Which GeoHash precision should you use for the geo-index lookup? Show your reasoning.

**Solution:**

```
Rule: choose precision P such that cell_size >= radius.
  Then 9 cells (3x3 grid) always covers the search circle.

GeoHash precision table:
  Precision 4: ~39km x 20km cell
  Precision 5: ~4.9km x 4.9km cell
  Precision 6: ~1.2km x 0.6km cell

For radius 20km:
  Precision 6: cell 1.2km, radius 20km >> cell size
    -> 9 cells cover only 3.6km x 1.8km. Far too small. Misses most of the 20km circle.
    -> Need a 17x34 grid of cells (17 x 1.2km = 20km in each direction). Too many cells.

  Precision 5: cell 4.9km, radius 20km >> cell size
    -> 9 cells cover 14.7km x 14.7km. Still smaller than the 40km diameter circle.
    -> Need about a 5x5 grid. 9 cells is not enough.

  Precision 4: cell ~39km x 20km, radius 20km <= 20km (the narrow dimension)
    -> The 9-cell grid covers 3 * 39km x 3 * 20km = 117km x 60km.
    -> A 20km radius circle (40km diameter) fits inside 60km x 60km. Safe.

Answer: Use precision 4 for a 20km radius search.

Trade-off: precision 4 cells are large (39km x 20km).
  Each cell likely has thousands of businesses.
  More candidates to Haversine-filter, but still manageable.
  Haversine for 10,000 candidates: 1ms. Acceptable.
```

---

### Exercise 6: International date line handling

**Problem:** A user at lon = 179.9 degrees searches for businesses within 50km. A business is at lon = -179.9 degrees (22km away across the date line). Why does the standard 9-cell approach fail, and how would you fix it?

**Solution:**

```
Why it fails:
  GeoHash encodes longitude by binary-splitting [-180, 180].
  lon = 179.9 and lon = -179.9 are at opposite ends of this range.
  Their GeoHash prefixes are completely different (e.g., "xz..." vs "b0...").
  The neighbor algorithm for "xz..." does not produce "b0..." as a neighbor.
  -> Business at -179.9 is never included in the 9-cell search from 179.9.

Fix 1: Dual search (simplest, handles L5 interview)
  If abs(user_lon) > 170:
    Search 1: (lat, lon = 179.9, radius = 50km) -> normal search
    Search 2: (lat, lon = 179.9 - 360 = -180.1, radius = 50km) -> wrapped search
      Note: normalize lon to [-180, 180] before encoding to GeoHash
      lon = -180.1 -> lon = -180.1 + 360 = 179.9 (same search) <- this doesn't work directly
    
    Correct wrapping:
      "From 179.9 looking west 50km" = cross the date line
      Equivalent search: lon = 179.9 - 360 = -180.1 -> clamp to -180
      But GeoHash understands -180, so search (lat, -180.0, 50km) to cover the western side

    Simpler: always run two searches near the date line and union the results.

Fix 2: Double-index businesses near the date line
  For any business with lon > 170: also index it under (lat, lon - 360)
    lon = -179.9 -> also store under lon = 180.1 (normalized to 179.9 + 360 - 360... )
  
  Simpler: if business lon < -170: also SADD it to the geohash for (lat, lon + 360 - 360)
  This allows searches from 179.9 to find businesses indexed at -179.9.

For the interview:
  "The date line affects < 0.1% of users. I handle it with Fix 1:
  detect abs(lon) > 170, run two searches, merge results, deduplicate.
  This adds one extra set of Redis calls for affected users but keeps
  the geo-index design simple for the 99.9% majority."
```

---

## Homework

### Short homework

**Short 1:** Go to geohash.org or use any online GeoHash encoder. Take your home address and 3 nearby businesses. Encode all to GeoHash precision 6. Verify: (a) do the closest two share a 5-character prefix? (b) at what precision do they first share a prefix? (c) decode the 8 neighbors of your home GeoHash precision 6 cell. Do the decoded centers match what you expect geographically?

**Short 2:** Implement `haversine(lat1, lon1, lat2, lon2) -> km` in Python. Test it against three known distances: (a) London to Paris (~341 km), (b) San Francisco to Los Angeles (~560 km), (c) two points 100m apart. How accurate is your implementation compared to Google Maps distance?

**Short 3:** Read the Redis documentation for `GEOADD` and `GEOSEARCH` (search "redis GEOSEARCH"). Answer: (a) what does Redis store internally for a geo-indexed member? (b) what is the precision of Redis's internal geo-encoding? (c) why would you choose custom Redis Sets (as in this chapter) over native GEOSEARCH for a category-filtered proximity service?

### Deep homework

**Deep 1:** Build a working proximity service in Python or Go:
- Backend: SQLite with 100,000 random businesses (lat, lon, category, name)
- Geo-index: Python dict mapping `"geo:{category}:{geohash6}"` -> set of business_ids
- Build the index from SQLite on startup
- API endpoint: `GET /nearby?lat=X&lon=Y&radius=R&category=C` -> top 20 results
- Implement: 9-cell neighbor search, Haversine filter, sort by distance
- Measure p99 latency for 10,000 random queries. Compare with and without the geo-index (use Postgres bounding-box query as baseline).

**Deep 2:** Benchmark GeoHash precision impact:
- Generate 1M random businesses worldwide
- For precision 4, 5, and 6 and radius 1km, 5km, 20km (9 combinations):
  - Run 1,000 random searches with the 9-cell approach
  - Measure: (a) false positive rate (businesses in cells but outside radius), (b) false negative rate (businesses within radius but in wrong cells), (c) number of candidates returned
- Plot a 3x3 grid of precision vs radius showing false positive/negative rates
- Which precision minimizes false negatives for each radius?

**Deep 3:** Read the S2 Geometry library overview at s2geometry.io. Google Maps uses S2 cells. Answer: (a) what shape is an S2 cell (vs GeoHash rectangle)? (b) why does S2 handle poles and the date line better? (c) how does S2 level (0-30) compare to GeoHash precision (1-12)? (d) for what use cases would you choose S2 over GeoHash? Write a 500-word comparison.

---

## Glossary

**GeoHash:** A geocoding system that encodes (latitude, longitude) into a short alphanumeric string. Nearby locations share a common prefix. The Earth is divided into a rectangular grid where each cell has a unique string name.

**GeoHash precision:** The length of the GeoHash string, controlling cell size. Precision 1 = continent (~5000km); precision 6 = neighborhood (~1.2km x 0.6km); precision 9 = room (~5m x 5m).

**QuadTree:** A 2D spatial data structure that recursively divides space into 4 quadrants. Adapts to data density: dense areas are subdivided more finely. Good for real-time moving objects and very uneven data distributions.

**R-tree:** A spatial index for disk-based storage, used by PostGIS and SQLite. Organizes objects by their minimum bounding rectangles. Supports arbitrary spatial queries (polygon search, intersects) but is slower than in-memory GeoHash.

**Haversine formula:** Computes the great-circle distance (shortest path along the Earth's surface) between two lat/lon coordinates. Assumes Earth is a perfect sphere. Accurate to 0.3% for most distances.

**Great-circle distance:** The shortest distance between two points on a sphere, measured along the sphere's surface. This is what Haversine computes, and what "distance between cities" means in practice.

**Candidate expansion:** A two-phase search pattern: (1) cheaply fetch all candidates from the spatial index (approximate), (2) compute exact distances and filter. Balances speed and correctness.

**Spatial index:** A data structure organizing objects by location, enabling efficient radius and bounding-box queries. Examples: GeoHash index, QuadTree, R-tree, KD-tree, S2 cells.

**GeoHash neighbor:** One of the 8 cells (N, NE, E, SE, S, SW, W, NW) physically adjacent to a given GeoHash cell. Used in radius searches to ensure coverage near cell boundaries.

**Cache stampede:** Multiple requests simultaneously finding a cached value expired and independently computing the fresh value, causing a spike in backend load. Prevented by jittered TTLs or probabilistic early expiration.

**Eventual consistency:** A consistency model where all replicas reach the same state eventually, but reads may see stale data temporarily. The geo-index in this design is eventually consistent: new businesses appear within 60 seconds.

**Outbox pattern:** A technique for atomic database write + event publish without distributed transactions. Write both the record and the event to the same database in one transaction. A poller publishes the event to the message broker separately.

**Hot partition (geo hot spot):** A geographic region (GeoHash cell) receiving disproportionately more traffic than others. Common near popular landmarks. Requires dedicated resources or key-level sharding.

**GEOADD / GEOSEARCH:** Redis commands for native geo-spatial indexing. `GEOADD` stores a (lon, lat, member) triple. `GEOSEARCH` finds members within radius using Haversine internally. Limitations: single-key (hard to shard by category).

**S2 cells:** Google's hierarchical geographic partitioning system. Uses a projection from the sphere to a cube face, producing cells with more uniform shape (closer to square) than GeoHash rectangles. Handles poles and the date line better than GeoHash.

---

## The One-Sentence Summary

> "Proximity service = GeoHash-indexed Redis Sets (center cell + 8 neighbors for any radius, precision matched to radius size) + Haversine distance filter on candidates + business detail cache in Redis + async Kafka pipeline for index updates — the key insight is that GeoHash collapses a 2D radius search into 9 fixed Redis key lookups, making 17,000 searches/sec achievable with no database reads on the hot path."

---

*Section 5 — L5 / Senior SWE. Very high frequency — asked at Google, Meta, Uber, Yelp, DoorDash.*  
*Full chapter. No other resource needed for this design.*

---

## Part 6: Algorithm Deep Dives

This section is for the cross-questioning phase of the interview. If an interviewer asks "walk me through GeoHash encoding" or "how does neighbor lookup actually work," you need to go one level deeper than high-level concept. This part gives you that depth.

---

### 6.1 GeoHash Encoding — Bit by Bit

**Analogy first.** Imagine you are searching for a house in an unknown city. You start with the question "is it in the northern or southern half?" That splits the world in two. Then "is it in the eastern or western half of that strip?" That splits it again. GeoHash is just this binary search game, played 30 times on longitude and 25 times on latitude, then the two resulting bit strings are shuffled together (interleaved), and the combined bit string is converted to a short human-readable code.

**Full worked example: San Francisco (lat=37.7749, lon=-122.4194)**

Step 1 — Encode longitude to 15 bits using binary search on [-180, 180]:

```
Range              Mid       lon=-122.4194   Bit
[-180, 180]        0         left of 0?  Yes  0
[-180,   0]       -90        left of -90? No  1
[ -90,   0]       -45        left of -45? Yes 0
[ -90,  -45]      -67.5      left of -67.5? Yes 0
[ -90,  -67.5]    -78.75     left of -78.75? Yes 0
[ -90,  -78.75]   -84.375    left of -84.375? Yes 0
[ -90,  -84.375]  -87.1875   left of -87.1875? Yes 0
...continuing to 15 bits...
```

After 15 iterations the longitude bits are: 0 1 0 0 0 1 1 0 0 0 0 1 0 1 0
(Exact values depend on remaining iterations; the pattern above shows the first 8.)

Step 2 — Encode latitude to 15 bits using binary search on [-90, 90]:

```
Range           Mid     lat=37.7749    Bit
[-90, 90]        0       above 0? Yes   1
[  0, 90]       45       above 45? No   0
[  0, 45]      22.5      above 22.5? Yes 1
[ 22.5, 45]    33.75     above 33.75? Yes 1
[ 33.75, 45]   39.375    above 39.375? No  0
[ 33.75,39.375] 36.5625  above 36.5625? Yes 1
...continuing to 15 bits...
```

After 15 iterations the latitude bits are: 1 0 1 1 0 1 0 1 1 1 0 0 0 1 1

Step 3 — Interleave: even positions = longitude bits, odd positions = latitude bits.

```
Position:  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14 ...
Source:   lon lat lon lat lon lat lon lat lon lat lon lat lon lat lon ...
Bit:       0   1   1   0   0   1   1   1   0   0   0   1   1   1   0 ...
```

Step 4 — Group into 5-bit chunks:

```
01100  11100  01110  ...
  12     28    14   (decimal values)
```

Step 5 — Map each 5-bit chunk to the base-32 alphabet:

```
Alphabet: 0123456789bcdefghjkmnpqrstuvwxyz
Index 12 -> 'e'
Index 28 -> 'u'
Index 14 -> 'g'
...
```

Result: San Francisco GeoHash at precision 5 starts with "9q8y..." (the exact letters depend on full 30-bit computation; this walkthrough shows the mechanics).

**Why this matters in an interview:** If asked "why does precision 5 cover a ~5km box?" you can explain: precision 5 = 25 bits total (13 lon + 12 lat) = 8 km × 5 km cell. More bits = smaller cell. The table is:

```
Precision  Bits   Cell size (approx)
    1        5     5,000 km x 5,000 km
    2       10       1,250 km x 625 km
    3       15         156 km x 156 km
    4       20           39 km x 20 km
    5       25            5 km x 5 km    <-- default for 5km radius
    6       30          1.2 km x 0.6 km  <-- for 0.5km radius
    7       35           153 m x 153 m
    8       40            19 m x 19 m
    9       45             2 m x 5 m
```

---

### 6.2 GeoHash Neighbor Lookup Table — Why String Arithmetic Fails

**The naive idea.** A common first-instinct answer is "to get the right neighbor, just increment the last character." This is wrong. GeoHash characters do not correspond to a simple linear axis. The cell to the right of "9q8y5" is NOT "9q8y6" because the base-32 encoding interleaves latitude and longitude bits, so incrementing the last character can cross latitude lines unexpectedly.

**The actual solution.** A static lookup table encodes, for each character in the base-32 alphabet, what character its neighbor is in each direction. There are two flavors of the table: one for even-length positions (longitude-dominant) and one for odd-length positions (latitude-dominant), because the interleaving alternates which axis the last bit belongs to.

The base-32 alphabet used by GeoHash:

```
0 1 2 3 4 5 6 7 8 9 b c d e f g h j k m n p q r s t u v w x y z
```

(Note: letters i, l, o are excluded to avoid visual confusion with numbers.)

For even-length hashes (last character encodes a longitude-dominant bit group):

```
Direction   Neighbor mapping (subset)
RIGHT (E)   b -> c, c -> f, f -> g, g -> u, u -> v, v -> y, y -> z ...
LEFT  (W)   0 -> 2, 2 -> 8, 8 -> b, b -> p, p -> r, r -> x, x -> z ...
TOP   (N)   p -> b, r -> c, x -> f, z -> g, b -> c  ...
BOTTOM(S)   same table read in reverse
```

**Why a table instead of math.** The bit interleaving means longitude and latitude bits are not contiguous — they alternate. When you increment the last character, you change bits that affect BOTH latitude and longitude simultaneously in a way that depends on the character's position (even vs. odd). Only a precomputed table that was derived from the full interleaving pattern gives the correct neighbor.

**Border cases.** When the last character is at the edge of the mapping (no valid neighbor in the table), you carry over to the previous character using a "border" table. This is exactly like carrying in binary addition. Most geohash libraries handle this for you, but you should know this complexity exists.

**Interview answer.** If asked "how do you find the 8 neighbors of a GeoHash cell," say: "Use a precomputed neighbor table (one for even-length, one for odd-length hashes). The table maps each base-32 character to its neighbor character in each cardinal direction. For edge characters, a border table handles carry-over to the preceding character. This gives exact neighbors in O(1) per direction."

---

### 6.3 QuadTree — Full Implementation Detail

**What a QuadTree node looks like in memory:**

```
Node {
  bounds: {
    min_lat, max_lat,
    min_lon, max_lon
  }
  is_leaf: boolean
  children: [Node, Node, Node, Node]   // NW, NE, SW, SE; null if is_leaf
  businesses: [BusinessID]             // only populated if is_leaf
}
```

**The threshold constant.** A leaf node holds at most MAX_ITEMS = 100 businesses. If you try to insert a 101st business, the leaf splits into 4 children and the 101 businesses are redistributed.

**Insert algorithm (pseudocode):**

```
function insert(node, business):
  if not node.is_leaf:
    child = find_quadrant(node, business.lat, business.lon)
    insert(child, business)
    return

  // node is a leaf
  node.businesses.append(business)

  if len(node.businesses) > MAX_ITEMS:
    split(node)

function split(node):
  mid_lat = (node.bounds.min_lat + node.bounds.max_lat) / 2
  mid_lon = (node.bounds.min_lon + node.bounds.max_lon) / 2

  node.children[NW] = new Node(min_lat=mid_lat, max_lat=node.bounds.max_lat,
                                min_lon=node.bounds.min_lon, max_lon=mid_lon)
  node.children[NE] = new Node(min_lat=mid_lat, max_lat=node.bounds.max_lat,
                                min_lon=mid_lon, max_lon=node.bounds.max_lon)
  node.children[SW] = new Node(min_lat=node.bounds.min_lat, max_lat=mid_lat,
                                min_lon=node.bounds.min_lon, max_lon=mid_lon)
  node.children[SE] = new Node(min_lat=node.bounds.min_lat, max_lat=mid_lat,
                                min_lon=mid_lon, max_lon=node.bounds.max_lon)

  for each biz in node.businesses:
    child = find_quadrant(node, biz.lat, biz.lon)
    child.businesses.append(biz)

  node.businesses = []
  node.is_leaf = false
```

**Search algorithm — collect all leaf nodes overlapping the query circle:**

```
function search(node, center_lat, center_lon, radius_km, results):
  if not circle_overlaps_rect(center_lat, center_lon, radius_km, node.bounds):
    return  // prune this entire subtree

  if node.is_leaf:
    for each biz in node.businesses:
      if haversine(center_lat, center_lon, biz.lat, biz.lon) <= radius_km:
        results.append(biz)
    return

  for each child in node.children:
    if child is not null:
      search(child, center_lat, center_lon, radius_km, results)

function circle_overlaps_rect(clat, clon, r_km, bounds):
  // Find nearest point on the rectangle to circle center
  nearest_lat = clamp(clat, bounds.min_lat, bounds.max_lat)
  nearest_lon = clamp(clon, bounds.min_lon, bounds.max_lon)
  dist = haversine(clat, clon, nearest_lat, nearest_lon)
  return dist <= r_km
```

**Depth calculation for Earth at 10m resolution.** The Earth is roughly 40,000 km in circumference. At 10m resolution, you need 40,000,000m / 10m = 4,000,000 cells across one axis. log2(4,000,000) ≈ 22 levels deep. A QuadTree representing all Earth geography at 10m resolution would be 22 levels deep. At 100m resolution (acceptable for business search) it would be about 19 levels deep.

**Why QuadTree vs GeoHash for interview.** Both are correct. GeoHash is simpler to implement in a distributed system (Redis SADD/SMEMBERS are native operations). QuadTree is better for adaptive density — dense cities get more splits, sparse areas get fewer, so queries are always fast. For this design we chose GeoHash because Redis supports it natively and simplicity beats marginal performance gain at this scale.

---

### 6.4 Redis Pipeline for 9-Cell Lookup

**Without pipelining — 9 round trips:**

```
client sends: SMEMBERS geohash:9q8y5:restaurant   --> waits ~1ms
client sends: SMEMBERS geohash:9q8y4:restaurant   --> waits ~1ms
client sends: SMEMBERS geohash:9q8y7:restaurant   --> waits ~1ms
... 6 more ...
Total: 9ms just for network round trips
```

**With pipelining — 1 round trip:**

```
// Build pipeline
pipeline = redis.pipeline()
for each cell_hash in [center, N, NE, E, SE, S, SW, W, NW]:
  pipeline.smembers("geohash:" + cell_hash + ":" + category)

// Send all 9 commands in one TCP packet, receive all 9 results together
results = pipeline.execute()

// Merge all results
candidates = union(results)
// Total: ~1ms
```

**Pseudocode for the full Location Service hot path:**

```
function search(lat, lon, radius_km, category):
  precision = radius_to_precision(radius_km)  // e.g., radius=5km -> precision=5
  center_hash = geohash_encode(lat, lon, precision)
  neighbors = geohash_neighbors(center_hash)  // returns list of 8 hashes
  all_cells = [center_hash] + neighbors       // 9 cells total

  // Stage 1: pipeline Redis to get candidate IDs
  pipeline = redis.pipeline()
  for cell in all_cells:
    pipeline.smembers("geo:" + cell + ":" + category)
  cell_results = pipeline.execute()

  candidate_ids = union_all(cell_results)    // deduplicate across cells

  // Stage 2: pipeline Redis to get lat/lon for each candidate
  pipeline2 = redis.pipeline()
  for id in candidate_ids:
    pipeline2.hget("biz:" + id, "lat")
    pipeline2.hget("biz:" + id, "lon")
  coord_results = pipeline2.execute()

  // Stage 3: Haversine filter
  final_candidates = []
  for i, id in enumerate(candidate_ids):
    biz_lat = coord_results[i*2]
    biz_lon = coord_results[i*2 + 1]
    dist = haversine(lat, lon, biz_lat, biz_lon)
    if dist <= radius_km:
      final_candidates.append((id, dist))

  // Stage 4: sort by distance
  final_candidates.sort(by=dist)
  return final_candidates
```

**Why pipelining is safe here.** The 9 SMEMBERS commands are independent — no result depends on another. Pipelining non-dependent commands is always safe and always faster. The savings grow with network latency: on cross-datacenter links (5-10ms RTT), pipeline savings jump from 8ms to 40-90ms saved.

---

## Part 7: Race Conditions and Concurrency

This is the section interviewers use to distinguish candidates who have shipped real systems from candidates who only know happy paths. Every distributed system has race conditions. Knowing the top 3 for this design — and their fixes — is the difference between a hire and a no-hire at the senior level.

---

### 7.1 Race Condition 1 — Business Location Update

**The scenario.** A business moves. The business owner updates their address in the Business Service. The system must: (1) remove the business from the old GeoHash cell in Redis, (2) add it to the new GeoHash cell.

**The race.** Two processes can interleave like this:

```
Process A (location update):           Process B (another update or rebuild):
T=0: HGET biz:123 -> lat=37.7, lon=-122.4
                                        T=1: SADD geo:9q8y5:restaurant 123
                                             (places biz at new location already)
T=2: SREM geo:9q8yf:restaurant 123     (removes from OLD cell -- correct)
T=3: SADD geo:9q8y5:restaurant 123     (adds to NEW cell -- now it's there twice? no, sets deduplicate)
                                        T=4: SREM geo:9q8y5:restaurant 123
                                             (Process B doing a delete? biz is now missing!)
```

The worst case: the business ends up in neither the old cell nor the new cell. It disappears from search results until the next index rebuild.

**The fix: Lua script for atomic update.** Redis executes Lua scripts atomically — no other command can run between the lines of a Lua script.

```
-- Lua script: atomic_location_update.lua
local biz_id = KEYS[1]
local old_cell = KEYS[2]
local new_cell = KEYS[3]
local new_lat  = ARGV[1]
local new_lon  = ARGV[2]
local category = ARGV[3]

-- Step 1: read current state (inside the atomic block)
local current_lat = redis.call('HGET', biz_id, 'lat')
local current_lon = redis.call('HGET', biz_id, 'lon')

-- Step 2: remove from old cell
redis.call('SREM', old_cell .. ':' .. category, biz_id)

-- Step 3: add to new cell
redis.call('SADD', new_cell .. ':' .. category, biz_id)

-- Step 4: update coordinate hash
redis.call('HSET', biz_id, 'lat', new_lat, 'lon', new_lon)

return 1
```

Because this entire script executes atomically, no other Redis command can interleave. The business is always in exactly one cell.

**Interview answer.** "We use a Redis Lua script to make the SREM (remove from old cell) + SADD (add to new cell) + HSET (update coordinates) operation atomic. Without this, a concurrent delete or rebuild can remove the business from both cells."

---

### 7.2 Race Condition 2 — Business Deleted During Search

**The scenario.** A user's search starts at T=0. At T=1, the business owner deletes their listing. The user's search fetches business IDs at T=0, then fetches details for each ID at T=2.

**The timeline:**

```
T=0: Search: SMEMBERS geo:9q8y5:restaurant  -> returns [123, 456, 789]
T=1: Delete: SREM geo:9q8y5:restaurant 123
             DEL biz:123
             (business 123 is now gone from Redis)
T=2: Search: HGET biz:123 lat  -> (nil) -- key does not exist
             HGET biz:123 lon  -> (nil)
             GET detail:123    -> (nil)
```

The search code gets a nil response when fetching details for business 123.

**Is this a bug? No. This is correct behavior.** The business was deleted. The user should not see it in results. The Location Service simply skips any business ID that returns nil on detail fetch. This is a graceful degradation pattern.

**The client-side handling:**

```
function fetch_details(candidate_ids):
  results = []
  for id in candidate_ids:
    detail = cache.get("detail:" + id)
    if detail is None:
      detail = db.get_business(id)  // will return None if deleted
    if detail is not None:
      results.append(detail)
    // if detail is None: skip this business, it was deleted mid-search
  return results
```

**Why this is a feature, not a bug.** The alternative — locking every business record for the duration of a search — would be catastrophically slow. Read-after-delete tolerance is the standard approach in eventually consistent systems. The user gets a slightly smaller result list, which is fine. The deleted business should not appear.

**The one edge case that is a bug.** If the business is deleted but its ID remains in the GeoHash Redis set (because the SREM failed or was not executed), it will keep appearing in candidate lists. This is why the deletion flow must atomically execute both the detail deletion AND the SREM from all cells — again, via a Lua script or a Kafka event consumed by the Index Update Worker.

---

### 7.3 Race Condition 3 — Index Rebuild Racing With Live Updates

**The scenario.** Every night, a batch job rebuilds the geo-index from Postgres to catch any drift (Redis evictions, missed Kafka events). The rebuild takes 30-60 minutes for 200M businesses. During that time, live business updates are still arriving via Kafka.

**The problem without coordination:**

```
T=0:    Rebuild starts. Reads Postgres snapshot.
T=15m:  Business 123 updates its location in Postgres.
T=15m:  Kafka event: "business 123 moved to new location"
T=15m:  Index Update Worker: SREM old_cell:123, SADD new_cell:123  (correct)
T=30m:  Rebuild reaches business 123 in its Postgres snapshot.
        Snapshot shows OLD location (taken at T=0, before the update).
        Rebuild: SREM new_cell:123, SADD old_cell:123  (WRONG -- reverts the live update!)
```

The rebuild overwrites the live update with stale data. Business 123 is now back in the wrong cell.

**The fix: blue-green index rebuild.**

```
Step 1: Rebuild writes to a NEW index namespace:
        Instead of "geo:9q8y5:restaurant", write to "geo_new:9q8y5:restaurant"

Step 2: During rebuild, live Kafka events continue writing to the CURRENT namespace:
        "geo:9q8y5:restaurant" is still the live index.
        Location Service reads from "geo:" (old) during rebuild.

Step 3: Rebuild completes. Apply all Kafka events that arrived during rebuild:
        The Kafka topic has a consumer lag offset — replay all events from T=0
        (rebuild start) to T=now against "geo_new:" namespace.

Step 4: Atomic namespace swap using a feature flag:
        Update config: ACTIVE_INDEX_PREFIX = "geo_new"
        All Location Service instances read from "geo_new:" immediately.

Step 5: After swap, delete old "geo:" namespace.
        Old namespace cleanup can be deferred 10 minutes for safety.
```

**Why replaying Kafka events works.** Kafka retains events for 7 days. At rebuild start, record the current Kafka offset. At rebuild end, replay all events from that offset against the new index. This catches every update that happened during the rebuild window.

**Interview answer.** "We use a blue-green index approach: rebuild to a shadow namespace, replay Kafka events from the rebuild start offset to catch up, then atomically flip a feature flag to point all Location Service instances at the new index. This avoids any window where rebuilding overwrites live updates."

---

## Part 8: Performance and Optimization

Performance questions at senior interviews are about two things: (1) can you calculate actual numbers from first principles, and (2) do you know which optimizations actually matter vs. which are premature. This part gives you both.

---

### 8.1 Hot Path Latency Analysis

**Every operation on the read path for a single search:**

```
Operation                              Count   Latency each   Total
------------------------------------------------------------- ------
geohash_encode(lat, lon, precision)      1       0.01ms        0.01ms
geohash_neighbors(center_hash)           1       0.01ms        0.01ms
Redis pipeline SMEMBERS x9              9       0.1ms (total)  0.1ms
  (all 9 sent in 1 round trip)
Union/deduplicate candidate IDs          1       0.01ms        0.01ms
Redis pipeline HGET lat/lon x N         N       0.1ms (total)  0.1ms
  (N=~200 candidates typical, 1 RTT)
Haversine distance x N               N=200      0.001ms each   0.2ms
Sort results by distance                 1       0.01ms        0.01ms
Redis GET detail cache x 20           20        0.05ms each    1.0ms
  (top 20 results, parallel or pipeline)
------------------------------------------------------------- ------
Total                                                         ~1.5ms internal
+ network from client to Location Service                     5-10ms
+ network from Location Service to Redis                      0.5-1ms
------------------------------------------------------------- ------
p50 end-to-end:                                              ~20ms
p99 end-to-end:                                              ~80ms (Redis tail latency)
```

**Where the budget goes.** The dominant cost is not computation — it is Redis round trips and detail cache fetches. This is why pipeline is critical (collapses 9 RTTs to 1) and why detail caching is critical (avoids Postgres reads on the hot path).

**What breaks p99.** Redis tail latency spikes when a GeoHash cell is a hot partition (thousands of businesses in a downtown area). SMEMBERS on a set with 5,000 members takes longer than SMEMBERS on a set with 50 members. Solution: cap set size by subdividing hot cells to a higher precision.

---

### 8.2 Redis Connection Pool Sizing

**The math, from first principles.**

Traffic: 17,000 searches/second (from capacity estimates earlier in this chapter).

Per search, Location Service makes approximately:
- 2 Redis pipeline calls (stage 1: SMEMBERS x9, stage 2: HGET x N)
- 1 pipeline call for detail fetches
- Total: ~30 Redis operations per search, bundled into 3 round trips

Each round trip takes ~0.5ms (including network + Redis processing).

```
Concurrent searches at any moment:
  17,000 searches/sec x 0.020 sec per search = 340 concurrent searches

Redis connections needed:
  340 concurrent searches x 3 Redis round trips in flight = 1,020 connections
  But round trips complete in 0.5ms so concurrency factor is:
  340 x 3 x 0.0005 sec / 0.020 sec = ~25 connections busy at steady state

Wait, let me redo this properly:
  Each search holds a Redis connection for ~1.5ms total (the 3 pipeline calls)
  At 17,000 searches/sec: connections busy = 17,000 x 0.0015 = 25.5 connections
  Add 3x headroom for bursts = 75 connections
  Per 10 Location Service instances: 75 / 10 = 7-8 connections per instance
  Actual deployment: pool of 20 connections per instance (with headroom for bursty traffic)
```

**The simpler rule of thumb.** Each Location Service instance handles 1,700 searches/sec. At 1.5ms per search for Redis ops, that is 1,700 x 0.0015 = 2.55 Redis "connection-seconds" used per second. A connection pool of 20 connections means each connection handles 0.127 searches concurrently — well under the limit. 20 connections per instance is the safe number.

**Why connection pools matter.** Without a pool, each search opens a new TCP connection to Redis. TCP connection setup takes 1-3ms (SYN + SYN-ACK + ACK). At 17,000 searches/sec, that is 17,000 connection setup operations per second — a huge overhead. Connection pooling amortizes TCP setup across thousands of requests.

---

### 8.3 Haversine Batch Optimization

**The naive approach (sequential):**

```
for each candidate in candidates:  // N=200
  dist = haversine(user_lat, user_lon, candidate.lat, candidate.lon)
  if dist <= radius: keep it
```

200 Haversine calls sequentially. Each call: ~5 microseconds (sin, cos, atan2). Total: 1ms.

**The optimized approach (vectorized).**

Instead of calling Haversine 200 times individually, pass all 200 lat/lon pairs at once to a vectorized math library. SIMD instructions (SSE2/AVX2 on modern CPUs) can process 4 or 8 floating point operations in the time of one operation.

```
// Vectorized pseudo-code
candidate_lats = array of 200 floats
candidate_lons = array of 200 floats

// All 200 computations in parallel using SIMD
dlat = candidate_lats - user_lat    // 200 subtractions in 25 SIMD ops (8-wide)
dlon = candidate_lons - user_lon    // 200 subtractions in 25 SIMD ops
a = sin(dlat/2)^2 + cos(user_lat) * cos(candidate_lats) * sin(dlon/2)^2
// above line: all 200 values computed in ~50 SIMD ops
distances = 2 * R * asin(sqrt(a))  // 200 values
mask = distances <= radius
result_ids = candidate_ids[mask]    // filter in one pass
```

**Result:** 200 Haversine calls vectorized ≈ 0.1ms vs 1ms sequential. 10x speedup. In practice most Location Service implementations do NOT need this optimization at this scale (1ms is fine for a 20ms budget), but knowing it exists shows depth.

**When it matters.** At 100x scale (2 billion businesses, 1,000 million daily users), the Haversine filter becomes a CPU bottleneck. Vectorized batch Haversine is one of the key optimizations Uber made in their H3 library design.

---

### 8.4 Memory-Optimized Redis Key Design

**The default design stores UUIDs as set members.**

A UUID looks like: "550e8400-e29b-41d4-a716-446655440000"
That is 36 characters. Redis stores each set member as a string. 36 bytes per member.

A GeoHash cell at precision 5 in a dense city might contain 500 businesses. 500 x 36 bytes = 18,000 bytes per cell. Across 200M businesses distributed across ~40M precision-5 cells (average 5 per cell): 200M x 36 bytes = 7.2 GB just for set membership.

**The optimized design: use integer business IDs.**

Map each UUID to a sequential integer when the business is first created. Store in a separate key-value lookup (business_uuid -> business_int_id). All geo set members use the integer.

An 8-byte integer (int64) in Redis: Redis actually stores small integers (< 9999) as raw integers, and larger ones as a string representation. But encoded as a packed integer in a Redis Sorted Set (ZADD with integer score) or using Redis IntSets (automatic for small integer-only sets):

```
Redis IntSet optimization: if all members of a Set are integers
and the set has fewer than 512 members, Redis automatically uses
a compact IntSet encoding -- ~8 bytes per member instead of 36.
```

**Memory savings calculation:**

```
UUID string in set: 36 bytes per business
Integer in IntSet:   8 bytes per business
Savings per business: 28 bytes
Total businesses: 200 million
Total savings: 200M x 28 = 5.6 GB saved on set membership alone
```

Additional savings: the HGET coordinate storage can also use compact encoding. A lat/lon pair stored as two separate float strings ("37.7749", "-122.4194") takes 7+9 = 16 bytes. Stored as a packed binary struct (two 32-bit floats) it takes 8 bytes. But Redis hash values are strings by default, so this requires a custom encoding layer.

**Interview answer.** "We use integer business IDs rather than UUID strings as Redis set members. Redis automatically applies IntSet encoding for integer-only sets under 512 members, dropping per-member cost from 36 bytes to 8 bytes. For 200M businesses this saves 5.6 GB of Redis memory."

---

## Part 9: Rollout and Operational Safety

Shipping a geo-indexed system safely is harder than building it. This section covers the operational procedures you need to know to answer "how would you deploy this?" and "what if something goes wrong?"

---

### 9.1 Deployment Stages for Location Service

The Location Service is stateless — it reads from Redis and Postgres, writes nothing of its own. This makes deployment relatively safe. Standard canary rollout:

```
Stage 1: Deploy new version to 1 of 10 instances (10% traffic)
  - Monitor for 30 minutes:
    - search latency p50 / p99 (alert if p99 > 200ms)
    - error rate (alert if > 0.1%)
    - Redis CPU / memory (alert if > 70%)
  - If healthy: proceed to Stage 2

Stage 2: Deploy to 5 of 10 instances (50% traffic)
  - Monitor for 30 minutes (same metrics)
  - If healthy: proceed to Stage 3

Stage 3: Deploy to all 10 instances (100% traffic)
  - Monitor for 1 hour
  - Done
```

**What makes Location Service deployment low risk.** The geo-index in Redis is not changed during a Location Service deployment. Only the application code changes. If the new code has a bug, you redeploy the old version — the Redis state is unaffected.

**What makes Location Service deployment higher risk.** If the new code changes the GeoHash precision it expects, it will misread the existing Redis index. This is the exception case covered in Section 9.2.

---

### 9.2 GeoHash Precision Migration

This is the hardest operational procedure in this system. Changing GeoHash precision (e.g., from precision 5 to precision 6) requires rebuilding the entire geo-index. All Location Service instances must switch simultaneously — a rolling upgrade would cause half the fleet to read precision-5 keys while the other half reads precision-6 keys, producing incorrect results.

**Migration plan:**

```
Step 1: Build new index alongside old (blue-green)
  - Rebuild script writes to "geo_v2:" prefix (precision 6)
  - Live traffic continues reading from "geo_v1:" prefix (precision 5)
  - Kafka events continue updating "geo_v1:" (old index stays current)
  - Duration: ~2 hours for 200M businesses

Step 2: Catch-up replay
  - Record Kafka offset at rebuild start
  - After rebuild completes, replay all Kafka events from that offset
    against "geo_v2:" namespace
  - Duration: ~10 minutes (catch up on 2 hours of events)

Step 3: Flush search result cache
  - Search results are cached keyed by (lat, lon, radius, category)
  - These caches assume precision-5 cell coverage
  - After precision change, old cached results are wrong (cells don't align)
  - Flush the entire search cache: DEL search:* or use a version-tagged key prefix

Step 4: Atomic flip via feature flag
  - Feature flag: GEO_INDEX_PREFIX = "geo_v2"
  - Deploy config change to all Location Service instances simultaneously
    (use a config push that all instances poll every 30 seconds)
  - All instances switch within one 30-second polling cycle

Step 5: Verify
  - Run spot checks: search for businesses in 5 test locations, verify results
  - Monitor p99 latency for 15 minutes

Step 6: Clean up old index
  - After 30 minutes of stable operation, delete "geo_v1:" namespace
  - This frees significant Redis memory
```

**Why the cache flush is critical.** Cached search results contain the result set for a given (lat, lon, radius). After a precision change, the GeoHash cells no longer match the precision used to build the cache. A search for restaurants within 5km of a location might return a cached result that was computed with the wrong cell boundaries. Cache flush is mandatory.

---

### 9.3 Rollback Procedure

**When to roll back.** p99 search latency spikes above 200ms for more than 5 minutes after a Location Service deployment. Or error rate exceeds 1%.

**Rolling back the Location Service (stateless):**

```
Step 1: Identify the previous stable version (Docker image tag or deployment ID)
Step 2: Run deployment of previous version to all 10 instances
  - Takes ~5 minutes
Step 3: Verify metrics return to baseline
```

Rolling back a stateless service is easy. The Redis geo-index is unchanged. No data migration needed.

**Rolling back a precision migration.** This is harder.

```
Step 1: Flip feature flag back to GEO_INDEX_PREFIX = "geo_v1"
  - All instances revert to reading old precision in one config push
Step 2: The "geo_v1:" index may now be stale (it stopped receiving Kafka updates
        during the precision migration period -- actually it did NOT, we kept
        the old index live during migration)
Step 3: If we did NOT keep "geo_v1:" live (i.e., we deleted it in Step 6):
  - Rebuild old index from Postgres
  - 2 hour rebuild time -- this is painful
  - This is why we wait 30 minutes before deleting the old index in Step 6
```

**The 30-minute hold rule.** Never delete the old index until 30 minutes of stable operation. This gives you a fast rollback window (just flip the feature flag, old index is still warm in Redis).

---

### 9.4 What Makes Geo-Index Rollouts Risky

**Risk 1: Precision mismatch.** If one Location Service instance uses precision 5 and another uses precision 6, searches that cross a cell boundary produce different results on different instances. Users notice inconsistency. This is why the precision flip must be atomic (all instances simultaneously via config push), not rolling.

**Risk 2: Cache poisoning after precision change.** If search caches are not flushed, stale results with wrong cell coverage persist until TTL expires (up to 10 minutes). Businesses near cell boundaries appear or disappear incorrectly. Always flush search cache before or during precision migration.

**Risk 3: Kafka consumer lag during rebuild.** If the Index Update Worker falls behind during the index rebuild (high Kafka consumer lag), live updates accumulate unprocessed. When the worker catches up after the flip, it may overwrite newer state with older state if the Kafka events are processed out of order. Solution: process Kafka events with idempotent upsert logic — always compare event timestamp with current state timestamp before applying.

**Risk 4: Redis memory pressure during blue-green rebuild.** Running two full geo-indexes simultaneously doubles Redis memory consumption. For this system that means 24-36 GB peak (12-18 GB normal). Size Redis with 2x headroom for the migration window.

---

## Part 10: Cost and Operational Considerations

Cost conversations at senior interviews show you think about building systems that a business can actually afford to run.

---

### 10.1 Major Cost Drivers

```
Component             Sizing              Monthly cost (approx)
--------------------------------------------------------------
Redis (geo-index)     12-18 GB always-on  $500-800/mo
                      (r6g.xlarge, 1 shard, 3 replicas)

Redis (cache)         8-12 GB always-on   $300-500/mo
                      (r6g.large, 1 shard, 3 replicas)

Location Service      10 x c5.xlarge      $1,400/mo
                      (4 vCPU, 8 GB RAM)

Business Service      3 x c5.large        $300/mo

Index Update Worker   2 x c5.large        $200/mo

Postgres (primary)    1 x db.r5.2xlarge   $1,000/mo
                      + 2 read replicas    $700/mo

Kafka                 3-node cluster       $800/mo

CDN/Load Balancer     Traffic-based        $300-500/mo
--------------------------------------------------------------
Total (rough)                              $5,500-6,200/mo
```

At 100 million daily active users this comes to roughly $0.0055-0.0062 per user per month. Extremely efficient.

---

### 10.2 Cost Optimization — Cache Hit Rate

**The math.** Assume current search result cache hit rate is 80%. Each cache miss triggers 9 Redis SMEMBERS calls (the full geo lookup). Each Redis SMEMBERS on a cell with 200 members takes 0.05ms of Redis CPU.

If we improve cache hit rate by 10 percentage points (80% -> 90%), we reduce cache misses by 50%:

```
Current: 17,000 searches/sec x 20% miss rate = 3,400 full geo lookups/sec
Improved: 17,000 searches/sec x 10% miss rate = 1,700 full geo lookups/sec
Reduction: 1,700 fewer geo lookups/sec

Redis CPU saved: 1,700 x 9 x 0.05ms = 765ms CPU per second = 0.77 CPU core
Redis cost of 1 CPU core: ~$50/month
Savings: ~$40/month from Redis compute
```

Small absolute saving, but the more important benefit is lower Redis latency during peak hours (fewer SMEMBERS ops per second = shorter queues).

**How to improve hit rate by 10%.** Increase cache TTL from 60s to 120s. Tradeoff: businesses that update their hours or close will show stale data for up to 2 minutes instead of 1 minute. For most applications this is acceptable.

---

### 10.3 On-Call Runbook — Top 5 Alerts

This section describes what to do when your pager goes off at 3am. Knowing these shows interviewers you have shipped and operated real systems.

---

**Alert 1: search_latency_p99 > 200ms for 5 minutes**

Meaning: Users are experiencing slow searches.

Diagnosis steps:
```
1. Check Redis memory usage: redis-cli INFO memory
   - If used_memory > 90% of maxmemory: Redis is evicting keys -> go to Alert 2
   
2. Check for hot partition: redis-cli --scan --pattern "geo:*" | xargs redis-cli DEBUG SLEEP 0
   - Look for specific geo cells with extremely large SMEMBERS results
   - A cell with 5,000+ members causes slow SMEMBERS

3. Check Location Service CPU: if CPU > 80%, Haversine filter is the bottleneck
   - Short term: scale out Location Service (add 5 more instances)
   - Long term: increase GeoHash precision for dense areas to reduce candidates

4. Check network: high RTT between Location Service and Redis causes latency
   - Verify Location Service and Redis are in the same AZ
```

Fix for hot partition: create a "geo:9q8y5_restaurant_overflow" Redis key on a different shard. Update Location Service to union results from both keys. This is manual sharding at the key level.

---

**Alert 2: Redis evictions > 0**

Meaning: Redis is running out of memory and evicting keys. Evicted geo-index entries mean businesses disappear from search results.

Diagnosis:
```
redis-cli INFO stats | grep evicted_keys
redis-cli INFO memory | grep used_memory_human
```

Immediate fix:
```
Option A (fast): Increase Redis maxmemory limit (if headroom on the server)
Option B (correct): Add a Redis shard (increase cluster size)
Option C (stopgap): Lower cache TTL to 30s to free memory faster
```

Root cause: the blue-green index rebuild might have left the old index in memory. Check: `redis-cli --scan --pattern "geo_v1:*" | wc -l`. If the old index is still there, delete it immediately.

---

**Alert 3: index_consumer_lag > 120 seconds**

Meaning: The Index Update Worker is falling behind on Kafka events. Business updates are not being applied to the geo-index. New businesses and location changes are delayed by more than 2 minutes.

Diagnosis:
```
kafka-consumer-groups --describe --group index-update-worker
  -> shows current offset, log end offset, and lag per partition
```

Fix:
```
1. If lag is growing: Index Update Worker is overloaded. Scale out: add 2 more workers.
2. If lag is steady (not growing): a temporary spike, monitor and wait.
3. If lag is very large (>10,000 events): replay might take hours. Check if
   Redis write performance is degraded (high Redis latency slows the worker).
```

---

**Alert 4: search_result_count = 0 for all queries**

Meaning: Searches are returning zero results. The geo-index in Redis is empty or all keys are missing.

Causes:
```
A. Redis cluster restarted without persistence -> all data lost
B. A runaway delete script cleared the geo: namespace
C. Feature flag pointing at wrong index prefix (geo_v2: but only geo_v1: exists)
```

Immediate action:
```
1. redis-cli DBSIZE  -> if 0: Redis is empty, trigger emergency rebuild
2. redis-cli --scan --pattern "geo:*" | head -10  -> verify keys exist
3. Check feature flag: GEO_INDEX_PREFIX should be "geo:" (or "geo_v1:" or "geo_v2:")
```

Emergency rebuild command:
```
// Trigger rebuild job manually
curl -X POST http://rebuild-service/api/rebuild?priority=emergency
// Monitor: kafka-consumer-groups --describe --group rebuild-worker
// ETA: ~2 hours for 200M businesses
// During rebuild: serve stale cache results only. Search quality degrades.
```

---

**Alert 5: business_write_failures > 0**

Meaning: Business Service is failing to write new or updated businesses to Postgres.

Causes:
```
A. Postgres primary is down or unreachable
B. Disk full on Postgres
C. Connection pool exhausted
```

Immediate check:
```
psql -h postgres-primary -U app -c "SELECT 1"
// If fails: Postgres is down. Check outbox table for event accumulation.
```

Outbox accumulation is the key risk: if Postgres is down, the outbox (which stores pending Kafka events) is also down. New business writes fail completely. This is acceptable for a few minutes but becomes a data integrity issue if prolonged.

Fix: route write traffic to Postgres read replica (if the replica is promoted to primary). This is a Postgres failover event, handled by the DBA team or automated failover (RDS Multi-AZ switches in ~30-60 seconds automatically).

**What NOT to do:** Do not try to write directly to Redis as a temporary store. This creates a consistency gap where Redis has data that Postgres does not, and there is no outbox to reconcile them.

---

## Part 10 Summary: The Three Numbers Every Senior Engineer Knows Cold

When asked about this system in an interview, you should have these ready without calculation:

```
Scale:     200M businesses, 100M daily users, 17,000 searches/second
Latency:   p50 = 20ms, p99 = 80ms (end to end, with Redis cache)
Storage:   52 GB Postgres, 12-18 GB Redis geo-index, 8-12 GB Redis cache
Cost:      ~$5,500-6,200/month total infrastructure
```

And the three design decisions that make this system work:

1. **GeoHash collapses 2D radius search into 9 Redis key lookups.** Without this, you would query a database with a complex spatial query for every search. With this, you do 9 O(1) Redis set lookups.

2. **Pipelining collapses 9 round trips into 1.** Without this, 9ms of network overhead per search. With this, 1ms.

3. **Async Kafka pipeline decouples business writes from index updates.** Without this, every business write must synchronously update both Postgres and Redis, causing write failures to cascade. With Kafka, a Redis failure does not affect business write availability.

---

## Interview Q&A -- Most Common Cross-Questions

These are the follow-up questions interviewers ask immediately after your design. Each answer is meant to be said out loud in under 60 seconds.

---

**Q1: What is GeoHash? How does it map (lat, lon) to a 1D string?**

GeoHash encodes a 2D coordinate into a short alphanumeric string by interleaving binary-search bits for longitude and latitude. For longitude, you repeatedly ask "is it in the left or right half?" and record 0 or 1. Same for latitude. You interleave those bits -- lon bit, lat bit, lon bit, lat bit -- group them into 5-bit chunks, and map each chunk to a base-32 character. The result is a string where longer strings mean smaller cells, and nearby locations share a common prefix most of the time. Precision 6 gives you a cell of roughly 1.2km by 0.6km.

---

**Q2: Why do you need to search 9 GeoHash cells (center + 8 neighbors) instead of just the center cell?**

A circle does not fit neatly inside one rectangle. Your user is likely not at the exact center of their GeoHash cell -- they could be near any edge or corner. If a user is near the south edge of their cell, businesses 50 meters away could be in the cell directly to the south. Searching only the center cell would miss them. By always searching the center cell plus all 8 cardinal and diagonal neighbors, you guarantee the search circle is fully covered regardless of where the user sits within their cell. The rule is: this works as long as the search radius is smaller than the cell width, which is why you pick the precision to match the radius.

---

**Q3: What is the difference between GeoHash and QuadTree? When would you use QuadTree over GeoHash?**

GeoHash divides the world into a fixed rectangular grid -- every cell at a given precision is the same size everywhere. Dense Manhattan and sparse Montana get identical cell sizes. QuadTree recursively subdivides a region into 4 quadrants only when a cell exceeds a threshold (say 100 businesses), so dense areas get finer cells and sparse areas get coarser ones. GeoHash wins for static businesses because it maps directly to Redis keys (simple string operations, O(1) lookup, no tree traversal needed). QuadTree wins for real-time moving objects -- like ride-sharing drivers -- where density is uneven and changes dynamically, and where you need fast insert/delete without rebuilding the index.

---

**Q4: Why is GeoHash precision 6 (1.2km x 0.6km) a common choice? How do you pick the right precision?**

The rule is: pick a precision where the cell size is smaller than the search radius. If the cell is smaller than the radius, a 3x3 grid of 9 cells always fully covers the search circle. Precision 6 (cell ~1.2km) is the right match for searches up to about 1km radius, which is the most common case for "nearby" queries on mobile (coffee shop, pharmacy, ATM). For a 5km radius you drop to precision 5 (cell ~4.9km); for 20km you drop to precision 4 (cell ~39km). The trade-off: lower precision means larger cells, more candidates per cell, and more Haversine filtering work -- but it is still fast because the Haversine step is cheap.

---

**Q5: What is the Haversine formula? Why not use Euclidean distance for geographic search?**

Euclidean distance treats latitude and longitude as linear axes and computes sqrt((lat2-lat1)^2 + (lon2-lon1)^2). This breaks because one degree of longitude is 111km at the equator but only 55km at latitude 60 degrees (Oslo), and near zero at the poles. Euclidean gives errors up to 25% at high latitudes or large radii. Haversine computes the great-circle distance along the Earth's surface using spherical trigonometry, and is accurate to 0.3% for all locations. The extra cost is six trig operations per call, roughly 100 nanoseconds -- negligible against a 100ms budget. For 200 candidates that is 0.02ms total.

---

**Q6: How do you handle the date line edge case (search near longitude 180 or -180)?**

GeoHash encodes longitude by binary-splitting the range [-180, 180]. Longitude 179.9 and longitude -179.9 are physically 22km apart but have completely different GeoHash prefixes -- "xz..." versus "b0..." -- so the standard neighbor lookup never links them. The fix at L5 is a dual search: if abs(user_lon) > 170, run two searches -- one with the real longitude and one with lon shifted by 360 degrees -- and union the results before deduplication. This adds one extra batch of Redis calls for less than 0.1% of users (those near the date line in eastern Russia, Alaska, or New Zealand) while keeping the geo-index design simple for everyone else.

---

**Q7: How do you handle the boundary problem -- a business is in one GeoHash cell but very close to the edge?**

This is exactly why you always search 9 cells. A business that sits 10 meters inside a cell boundary is in one GeoHash cell, but a user 20 meters away on the other side of the boundary is in a different cell. If you searched only one cell you would miss that business. The 9-cell (center + 8 neighbors) approach guarantees that any business within the search radius is found as long as the radius is smaller than the cell width. After fetching all candidates from all 9 cells, you run the Haversine exact filter to discard businesses that are in the cells but geometrically outside the radius circle. This two-phase approach handles all boundary cases correctly.

---

**Q8: What is the two-phase search strategy (broad filter + exact filter)?**

Phase 1 is the broad filter: use GeoHash to cheaply fetch all candidate business IDs from the 9 relevant cells. This is approximate -- GeoHash cells are rectangles, not circles -- so you get some false positives (businesses in the cell corners that are outside the radius). Phase 2 is the exact filter: for each candidate, compute the exact Haversine distance and keep only those within the radius. Then sort by distance and return the top N. Phase 1 is O(9 Redis lookups) and runs in about 1ms. Phase 2 is O(candidates) Haversine calls at 100ns each. The combination is fast and correct.

---

**Q9: How does Redis store the geo-index? What Redis data structure is used?**

We use Redis Sets keyed by "geo:{category}:{geohash}". Each key maps to a Set of business IDs in that cell and category. Adding a business is SADD -- O(1). Removing is SREM -- O(1). Fetching all IDs in a cell is SMEMBERS -- O(N) where N is the set size, typically small. We also store per-business coordinates in a Redis Hash keyed by "business:{id}", with lat and lon fields, so the Location Service can run Haversine without hitting Postgres. Redis automatically uses compact IntSet encoding when all set members are integers and the set is small, cutting per-member memory from 36 bytes (UUID string) to 8 bytes.

---

**Q10: How do you keep the geo-index in sync when a business updates its location?**

When a business owner submits a location change, the Business Write Service updates Postgres synchronously and publishes a "business_updated" event to Kafka. The Index Update Worker consumes this event and performs a three-step Redis operation: SREM the business ID from the old GeoHash cell, SADD it to the new GeoHash cell, and HSET the new coordinates in the business hash. To prevent race conditions, these three operations are executed as a single atomic Redis Lua script. The propagation lag is typically under 60 seconds. As a nightly safety net, a batch job rebuilds the index from Postgres using a blue-green approach so no live traffic is disrupted.

---

**Q11: How do you handle a search radius that spans multiple GeoHash precision levels?**

You pick one precision per search based on the radius, not a mix. The rule is: use the precision where the cell size is smaller than the radius. For radius up to 1km, use precision 6 (cell ~1.2km). For 1-5km, use precision 5 (cell ~4.9km). For 5-50km, use precision 4 (cell ~39km). The index stores every business at all relevant precisions, or you build separate indexes per precision level and route the search to the correct one. You never mix precisions within a single search because then the 9-cell guarantee breaks -- cells at different precisions do not align. The trade-off is that lower precision means larger cells and more candidates to Haversine-filter, but this is still fast.

---

**Q12: What is the read/write ratio for a proximity service? How does that affect your caching strategy?**

For static businesses, the ratio is roughly 8,000:1 -- about 17,000 reads per second versus 2 writes per second. This extreme imbalance means the entire system should be optimized for reads. The geo-index lives in Redis (in-memory, not disk). Business details are cached in Redis with a 5-minute TTL so Postgres sees almost no read traffic. Search results for popular queries are cached for 60 seconds. The write path can tolerate eventual consistency (60-second index propagation lag) because writes are so rare. Every design decision -- Redis over Postgres for the index, caching at every layer, async index updates -- is justified by this ratio.

---

**Q13: How do you cache proximity search results? What is the cache invalidation strategy?**

The cache key is built from category, a coarsened location (GeoHash precision 4, which is a ~39km cell), and a bucketed radius (0-1km, 1-5km, 5-20km, 20-50km). Using precision 4 instead of exact coordinates means users within 39km of each other share the same cache entry for the same query -- high hit rate for dense urban areas. TTL is 60 seconds. Invalidation strategy: when a business in a given GeoHash area is added, updated, or deleted, the Index Update Worker deletes all search cache keys covering that precision-4 cell. This is a pattern of key-prefix deletion (DEL "search_cache:{category}:{precision4_hash}:*"). No complex invalidation logic needed because the cache is short-lived by design.

---

**Q14: What is a cache stampede for proximity search? How do you prevent it?**

A cache stampede occurs when a popular cache key expires and many requests simultaneously find a cache miss, each independently computing the result and writing back to cache. For proximity search near Times Square, this means millions of users simultaneously triggering full geo-index lookups when the 60-second cache expires -- spiking Redis CPU. Two mitigations: First, probabilistic early expiration -- when TTL falls below 10% remaining, 10% of requests proactively recompute and refresh the cache before it expires, so the cache is always warm. Second, a distributed mutex -- when a cache miss is detected, acquire a per-key lock; only the winner recomputes, others wait briefly then read the freshly populated cache.

---

**Q15: How do you rank results within the search radius (distance, rating, open now)?**

The geo-index returns only distance. All secondary ranking is a post-filter applied by the Location Service after the Haversine step. Distance is the primary sort. Rating is fetched from the business detail cache (already loaded for the top results). "Open now" is computed client-side from the hours data in the business detail response, or server-side as a boolean filter applied after Haversine. The key principle is that secondary filters are never pushed into the geo-index -- doing so would require separate indexes per filter combination, which explodes storage. The geo-index does one thing: spatial proximity. Everything else is post-processing on the small result set.

---

**Q16: How would you handle real-time location (e.g., moving food delivery drivers) vs static locations (restaurants)?**

These are fundamentally different problems that should be separate systems. For static businesses (restaurants), GeoHash in Redis with async Kafka updates is ideal -- locations change rarely, eventual consistency is fine. For real-time moving objects (drivers), you need a different approach: drivers send location updates every 5-10 seconds, the index must reflect changes within 1-2 seconds, and the write rate is orders of magnitude higher (1 million drivers x 0.1 updates/sec = 100,000 writes/sec). For drivers you would use a QuadTree with in-place atomic updates, or Redis native GEOADD with per-driver location keys and a TTL so stale drivers auto-expire. The two systems share no infrastructure.

---

**Q17: What is the scalability bottleneck -- reads or writes? How do you scale the bottleneck?**

Reads are the bottleneck at 17,000 searches/second versus 2 writes/second. The read bottleneck has two layers: the Location Service (stateless, easy to scale horizontally by adding instances behind the load balancer) and the Redis geo-index (stateful, harder). Redis scales reads via read replicas -- add 2-4 read replicas for the geo-index and route Location Service reads to replicas. If a single GeoHash cell becomes a hot partition (dense urban area with 100,000 searches/sec hitting the same cell), add a dedicated Redis shard for that cell prefix and distribute reads across it. At extreme scale (10x), you pre-aggregate popular cells into a CDN edge cache with a 10-second TTL to absorb read traffic before it hits Redis.

---

**Q18: How does your system handle a user who moves while searching (their location changes between requests)?**

Each search request is fully stateless -- the user sends their current GPS coordinates with every request, and the system computes fresh results each time. There is no session state tracking the user's movement. If the user moves 500 meters between two searches, the second request uses the new coordinates and returns updated results. The only subtlety is search result caching: if two requests from the same user land on the same precision-4 cache cell (roughly 39km), they return the same cached result even though the user moved. This is acceptable because the results are still within the search radius for both positions. If the user moves across a precision-4 boundary, they get a cache miss and fresh results automatically.

---

*Extended depth sections for cross-questioning readiness. Append to Chapter 61c.*
