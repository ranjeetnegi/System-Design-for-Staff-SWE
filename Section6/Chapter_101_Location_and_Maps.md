# Chapter 87: Location & Mapping — Uber / Google Maps

> "Design Uber" or "Design Google Maps" is the canonical geo-systems interview question.
> It tests spatial indexing, real-time location tracking, routing algorithms, and
> ETA estimation — four distinct systems that must compose cleanly under time pressure.
> Most candidates blur these together and lose the interview. This chapter teaches you
> to separate them, size them, and defend every design decision with numbers.

---

## Why This Chapter Matters

Geo-systems questions appear at Uber, Lyft, DoorDash, Google, Meta (location features),
Snap (Snap Map), and any company with a physical-world component. The unique challenge:
location data is continuous (not discrete like user IDs), requires spatial indexing (not
standard B-trees), has real-time update requirements (driver location every second), and
routing runs on a graph with over 100 million nodes. A candidate who treats this like a
standard social feed design will fail. A candidate who knows geohash prefix expansion,
Redis GeoSets, and Contraction Hierarchies will stand out at every level.

---

## Part 1: The Location Problem — Two Very Different Problems

### 1.1 What Uber and Google Maps Actually Do (And Why They Are Different)

When an interviewer says "design Uber" or "design Google Maps," they are actually asking
you to design several different systems that happen to all involve coordinates. Candidates
who treat these as one problem almost always run out of time or produce a muddled design.
The first thing you need to do — in the interview — is split the problem.

**Problem A: Driver Tracking (Real-Time Location Updates)**

This is a write-heavy, low-latency stream processing problem. Every driver app sends
its GPS coordinates to Uber's servers roughly every 4 seconds. At Uber's scale — about
5 million active drivers globally — that is over a million location updates arriving
every second during peak hours. Each update needs to be stored (so you can answer
"where is driver X right now?") and indexed (so you can answer "which drivers are within
2 km of this passenger?"). The data is extremely hot: you care about the last 30 seconds,
not the last year. Old locations expire and become worthless almost immediately.

**Problem B: Map Routing (Shortest Path on a Road Network)**

This is a graph algorithm problem. The road network is a directed weighted graph with
about 100 million nodes (intersections) and over 1 billion edges (road segments). Finding
the fastest route from San Francisco to Los Angeles on this graph naively would take
minutes. Google Maps answers in under 200 milliseconds. That speed requires offline
preprocessing that happens over days, not the runtime query itself. The data changes
slowly — roads don't move — but the weights on edges (travel time) change constantly
due to traffic.

**Problem C: ETA Prediction**

Even after you have the shortest route, you need to predict how long it will take.
"Shortest" is not always "fastest." A 10-mile route on a highway may be faster than a
6-mile route through downtown at 5 PM. ETA requires a machine learning model that
combines historical travel time data with real-time traffic probe data. This is a data
pipeline problem as much as a systems design problem.

**The Interview Move**

When the interviewer says "design Uber," your first response should be: "There are three
separate systems here — driver location tracking, proximity search, and routing/ETA.
Given 45 minutes, I'd like to focus on the first two, go deep on the location service
and spatial indexing, and then do a lighter sketch of routing. Does that sound right?"
This immediately signals you know the problem space and can make scope decisions.

### 1.2 Scale Numbers (Memorize These)

| Metric | Value | Why It Matters |
|--------|-------|----------------|
| Uber active drivers (peak) | ~5M globally | Sets write throughput |
| Location update frequency | Every 4 seconds | 5M / 4 = 1.25M writes/sec |
| Proximity search radius | 2–5 km | Sets geohash precision |
| Concurrent passenger queries | ~500K/sec | Sets read throughput |
| OSM road network | 100M nodes, 1B+ edges | Sets routing complexity |
| Geohash precision 6 | 1.2 km × 0.6 km cell | Key spatial resolution |
| Redis GeoSet query latency | < 1 ms | Enables <100ms response |
| CH routing query latency | < 1 ms | Why preprocessing matters |
| ETA accuracy target | ±2 min for p50 | Business requirement |
| Map tile cache hit rate | > 99% | Tiles are mostly static |

The 1.25M writes/second number is the single most important number in this problem.
Everything about the architecture flows from needing to ingest over a million GPS updates
per second while simultaneously answering proximity queries in under 100 milliseconds.

### 1.3 Latency Requirements

Uber's internal SLA for "find nearby drivers" is under 100 milliseconds end-to-end.
This sounds easy until you realize it includes network round-trip from the passenger's
phone, plus database query, plus Haversine distance calculation, plus sorting. To hit
that SLA you need in-memory storage (Redis, not Postgres), pre-indexed spatial data
structures, and horizontal scaling. You cannot afford a disk seek in this hot path.

Google Maps' routing SLA is under 200 milliseconds for a driving route query anywhere
in the world. That is only achievable because the actual graph search is running on a
preprocessed shortcut graph, not the raw OSM data.

### 1.4 Interview Brainstorming Q&A

**Q: Why not just use a SQL database with latitude and longitude columns and a WHERE
clause to find nearby drivers?**

A standard SQL query like `WHERE lat BETWEEN X-0.02 AND X+0.02 AND lng BETWEEN Y-0.02
AND Y+0.02` would technically work at small scale. The problem is that a B-tree index
only works efficiently on one dimension at a time. To filter on both latitude and
longitude simultaneously, the database would have to scan one dimension (say, all rows
within the latitude band) and then filter the results for longitude. For a table with
5 million rows updating every 4 seconds, with hundreds of thousands of proximity queries
running simultaneously, this approach collapses immediately. PostGIS adds spatial indexes
(R-trees) that partially solve this, but at 1M+ writes/second even PostGIS cannot keep
up — and you'd need dozens of database shards, at which point the operational complexity
is enormous.

The fundamental issue is that geographic proximity is a 2D property, and standard
database indexes are 1D. The entire field of spatial indexing — geohash, quadtrees, S2,
R-trees — exists to solve this exact problem: efficiently map 2D proximity to 1D
lookups that existing storage systems can handle.

**Q: Can't we just keep everything in memory? Seems simpler.**

We actually do keep the hot location data in memory — that is what Redis GeoSets are
for. But "everything in memory" is not a complete answer because you still need an index
within memory. Storing 5 million (driver_id, lat, lng) tuples in a flat array still
requires O(N) scan to answer a proximity query. Redis GeoSets solve this by encoding
each location as a geohash and storing it in a sorted set — the encoding turns a 2D
proximity lookup into a sorted-set range query that Redis can answer in O(log N + K)
time. So "keep it in memory" is right, but you also need "and use a spatial index within
that memory store."

**Q: How do you handle drivers going offline or the app crashing?**

This is an operational detail that L6 candidates know cold. Every driver update is
treated as a heartbeat. When the location service receives an update, it stores the
coordinates AND a timestamp. A separate background process (or Redis TTL) marks drivers
as offline if they have not sent an update in N seconds (Uber uses roughly 30 seconds).
This prevents "ghost drivers" — drivers that appear available to the matching system but
are actually offline. The matching service only considers drivers whose last_seen
timestamp is within the offline threshold. In Redis, you can implement this by storing
a TTL key per driver that expires after 30 seconds; if the key exists, the driver is
online.

---

## Part 2: Spatial Indexing — Geohash, Quadtree, S2

### 2.1 Why We Need a Spatial Index

Imagine you have 5 million drivers, each with a (latitude, longitude) pair. A passenger
in downtown Manhattan wants to see all drivers within 2 km. How do you answer this
efficiently?

The naive approach: loop through all 5 million drivers, compute the distance from each
to the passenger, return those under 2 km. This is O(N) — 5 million distance calculations
for every single passenger query. With 500,000 passenger queries per second, you need
2.5 × 10^12 operations per second. That is not happening.

The solution: a spatial index. A spatial index organizes points in space so you can
quickly find all points near a query location without checking every point. The three
main approaches used in production are geohash, quadtrees, and S2 geometry.

### 2.2 Geohash — Turning 2D into 1D

Geohash is the most widely used approach in backend systems because it is simple to
implement, works with any sorted key-value store, and the encoding is human-readable.

**The Core Idea**

The Earth's surface is divided into a grid of cells. Each cell has a string identifier.
The key property: cells that share a common prefix are geographically close. "9q8yy" is
a cell roughly 38m × 19m near San Francisco. "9q8y" is the parent cell, roughly 153m × 153m.
"9q8" is the grandparent, roughly 1.2km × 0.6km.

**How the Encoding Works**

Geohash uses a recursive binary subdivision. Start with the whole Earth, with longitude
ranging from -180 to +180 and latitude from -90 to +90.

Step 1: Bisect longitude. If your point is in the right half (0 to +180), write "1".
If left half (-180 to 0), write "0". Then bisect whichever half contains your point.

Step 2: Bisect latitude. Alternate between bisecting longitude and latitude.

Step 3: After 5 bits (alternating lon/lat), you have a 5-bit binary number. Encode it
as a base-32 character using the geohash alphabet (0-9, b-z minus a, i, l, o).

Step 4: Repeat. Each additional character adds 5 more bits of precision.

```
GEOHASH PRECISION TABLE:

Length | Cell Size          | Example
-------|--------------------|---------
  1    | 5,009 km × 4,992 km | "9"
  2    | 1,252 km × 624 km  | "9q"
  3    | 156 km  × 156 km   | "9q8"
  4    | 39 km   × 19 km    | "9q8y"
  5    | 4.9 km  × 4.9 km   | "9q8yy"
  6    | 1.2 km  × 0.6 km   | "9q8yym"
  7    | 153 m   × 153 m    | "9q8yymz"
  8    | 38 m    × 19 m     | "9q8yymzu"

For Uber proximity search (2km radius), precision 6 is the right choice.
```

**ASCII Diagram: Geohash Grid**

```
  Longitude →
  -180                 0                +180
  |_____________________|___________________|
  |         |           |         |         |
  |    b    |     c     |    f    |    g    |  ↑
  |_________|___________|_________|_________|  |
  |         |           |         |         |  L
  |    8    |     9     |    d    |    e    |  a
  |_________|___________|_________|_________|  t
  |         |           |         |         |  i
  |    2    |     3     |    6    |     7   |  t
  |_________|___________|_________|_________|  u
  |         |           |         |         |  d
  |    0    |     1     |    4    |     5   |  e
  |_________|___________|_________|_________|  |
                                               ↓
  Each first-level cell is ~5000km × 5000km.
  San Francisco is in cell "9" → "9q" → "9q8" → "9q8y" → ...

  ZOOM INTO CELL "9q8" (San Francisco area, ~156km × 156km):
  
  |----|----|----|----|----|----|----|----|
  | 9q8b| 9q8c| 9q8f| 9q8g| 9q8u| 9q8v| 9q8y| 9q8z|
  |----|----|----|----|----|----|----|----|
  | 9q88| 9q89| 9q8d| 9q8e| 9q8s| 9q8t| 9q8w| 9q8x|
  |----|----|----|----|----|----|----|----|
  | 9q82| 9q83| 9q86| 9q87| 9q8k| 9q8m| 9q8q| 9q8r|
  |----|----|----|----|----|----|----|----|
  | 9q80| 9q81| 9q84| 9q85| 9q8h| 9q8j| 9q8n| 9q8p|
  |----|----|----|----|----|----|----|----|
  
  Note: the ordering looks "scrambled" — this is the base-32 encoding.
  But cells with the same prefix ARE geographically close.
```

**The Boundary Problem**

Here is the critical flaw in geohash that almost every candidate misses. Two points that
are very close geographically can have completely different geohash prefixes if they sit
on opposite sides of a cell boundary.

Example: Point A is at 37.7749° N, 122.4194° W (San Francisco). Its geohash-6 is
"9q8yym". Now imagine Point B is 50 meters to the west, at 37.7749° N, 122.4200° W.
Its geohash-6 is "9q8yyj". They share only the 4-character prefix "9q8y". A prefix
scan for "9q8yym" would completely miss Point B, even though they are 50 meters apart.

The fix: always check the 8 neighboring cells of the target geohash cell. Every geohash
cell has exactly 8 neighbors (N, NE, E, SE, S, SW, W, NW). Libraries like `python-geohash`
provide a `neighbors()` function. Your proximity query becomes: fetch all drivers in the
target cell AND all 8 neighbors, then filter by actual Haversine distance.

```
GEOHASH BOUNDARY PROBLEM:

Cell "9q8yym"    Cell "9q8yyj"
+---------------+---------------+
|               |               |
|       A   *   |   * B         |
|           ←50m→               |
|               |               |
+---------------+---------------+

A and B are 50m apart but in different cells.
Prefix scan for "9q8yym" returns A but misses B.
FIX: also scan the 8 neighbors of "9q8yym".

THE 9-CELL QUERY PATTERN:
+-------+-------+-------+
| NW    |  N    | NE    |
|9q8yyh |9q8yyk |9q8yys |
+-------+-------+-------+
|  W    |TARGET | E     |
|9q8yyj |9q8yym |9q8yyt |
+-------+-------+-------+
| SW    |  S    | SE    |
|9q8yy7 |9q8yyk |9q8yyu |
+-------+-------+-------+
Scan all 9 cells, then filter by Haversine distance.
```

### 2.3 Quadtree — Adaptive Density

A quadtree is a tree data structure where each node represents a rectangular region of
space and has exactly four children: NW, NE, SW, SE. The tree is built by recursively
subdividing regions that contain too many points.

**Why Quadtrees Beat Geohash for Non-Uniform Density**

Geohash uses a uniform grid — every cell at a given precision level is the same size.
But driver density is wildly non-uniform. Manhattan might have 10,000 drivers in 59 km²
(170 drivers/km²) while rural Montana might have 1 driver in 100,000 km². A uniform
grid either wastes memory with tiny cells in rural areas or has cells too large to be
useful in urban areas.

Quadtrees adapt: they subdivide dense areas deeper and leave sparse areas as large cells.

```
ASCII DIAGRAM: ADAPTIVE QUADTREE

Level 0:
+---------------------------+
|                           |
|       WHOLE CITY          |
|                           |
+---------------------------+

Level 1 (subdivide because >N drivers):
+-------------+-------------+
|             |             |
|   NW quad   |   NE quad   |
|             |  (urban,    |
|             |  dense)     |
+-------------+-------------+
|             |             |
|   SW quad   |   SE quad   |
|  (rural,    |             |
|  sparse)    |             |
+-------------+-------------+

Level 2 (only NE quad subdivides further):
+-------------+------+------+
|             | NW   | NE   |
|   NW quad   |      |      |
|  (leaf)     +------+------+
|             | SW   | SE   |
+-------------+      |      |
|             +------+------+
|   SW quad   |             |
|  (leaf)     |   SE quad   |
+-------------+  (leaf)     |
                             |
+---------------------------+

Urban NE quad subdivides 4+ more levels.
Rural SW quad stays as a single leaf.

TREE STRUCTURE:
Root
├── NW (leaf: 50 drivers)
├── NE (split)
│   ├── NW (leaf: 200 drivers)
│   ├── NE (split)
│   │   ├── NW (leaf: 400 drivers)
│   │   ├── NE (leaf: 350 drivers)  ← Manhattan core
│   │   ├── SW (leaf: 410 drivers)
│   │   └── SE (leaf: 380 drivers)
│   ├── SW (leaf: 180 drivers)
│   └── SE (leaf: 220 drivers)
├── SW (leaf: 12 drivers)
└── SE (leaf: 75 drivers)
```

**Quadtree Limitations**

The main downside of quadtrees in production is that they are harder to distribute across
multiple machines than geohash. Geohash is just a string prefix — you can shard by prefix
across Redis nodes trivially. A quadtree is a tree data structure that traditionally lives
in a single process. You can shard it (each subtree lives on a different machine) but the
implementation complexity is significant. For this reason, many production systems
(including Uber) use geohash for the distributed storage layer and use quadtrees in
read-path caches within a single process.

### 2.4 S2 Geometry — Google's Approach with the Hilbert Curve

S2 is Google's spatial indexing library, open-sourced and now used by Google Maps,
DoorDash, Pokémon Go, and Foursquare. It is based on a mathematical object called the
Hilbert curve.

**What is the Hilbert Curve?**

The Hilbert curve is a fractal that fills 2D space. The key property: points that are
close in 2D space tend to be close on the 1D Hilbert curve. This is called "locality
preservation." Geohash also attempts locality preservation, but it does it imperfectly —
the boundary problem exists because geohash's base-32 encoding breaks locality at cell
edges. The Hilbert curve preserves locality much more smoothly.

```
HILBERT CURVE — SPACE-FILLING CURVE:

Level 1:        Level 2:              Level 3:
+--+            +--+--+               +-+-+-+-+
|  |            |  |  |               | | | | |
+--+    →       +--+--+      →        +-+-+-+-+
                |  |  |               | | | | |
                +--+--+               +-+-+-+-+
                                      | | | | |
                                      +-+-+-+-+
                                      | | | | |
                                      +-+-+-+-+

The curve visits every cell exactly once.
Points close in 2D → tend to be close in 1D index.
(Better locality than geohash's Z-order curve)
```

**S2 Cells**

S2 maps the Earth's surface onto 6 faces of a cube, then subdivides each face using the
Hilbert curve. This gives 30 levels of subdivision:

- Level 0: 6 cells (the 6 cube faces), each ~85 million km²
- Level 12: ~2 km² per cell (roughly the size of a New York City block)
- Level 15: ~30,000 m² per cell (half a city block)
- Level 30: individual square centimeters

S2 cell IDs are 64-bit integers. The hierarchical structure means that containment
queries are simple integer comparisons. The S2 library provides a "cell covering" function:
given any shape (circle, polygon, route corridor), return the minimal set of S2 cells
that cover the shape. This turns any 2D spatial query into a set of integer range queries.

**When to Choose What**

| Approach | Best For | Downside |
|----------|----------|----------|
| Geohash | Simple systems, any sorted KV store | Boundary problem, must check 9 cells |
| Quadtree | Adaptive density, games, single-machine | Hard to distribute |
| S2 | Complex shapes, best locality | Library dependency, more complex |

For the interview: geohash is easier to explain and defend. S2 is more impressive to
mention but you need to actually understand the Hilbert curve to explain it convincingly.
If you say "Google uses S2 because the Hilbert curve preserves locality better than
geohash's Z-order encoding" you will impress an L6 interviewer. If you just say "I'd
use S2 because Google uses it" that backfires.

### 2.5 Intern → Staff Progression: Spatial Indexing

**Intern:** "I'd store lat/lng in a database and use PostGIS for spatial queries."
(Functional but won't scale. No awareness of write throughput problem.)

**Junior (L3):** "I'd use geohash, encode each driver's location, and do prefix scans."
(Right idea, misses boundary problem.)

**Mid-Level (L4):** "Geohash prefix scan, check 8 neighbors to fix boundary problem,
filter by Haversine distance." (Correct. Knows the fix.)

**Senior (L5):** "Geohash in Redis sorted sets, precision 6 for 2km radius queries.
Shard Redis by geohash level-2 prefix so all drivers in a region are co-located.
Check 9 cells (target + 8 neighbors), then Haversine filter. Consider S2 for irregular
search shapes like surge pricing zones."

**Staff (L6):** "I'd use geohash for the hot path because it maps cleanly to Redis sorted
sets and the sharding story is simple. But I'd also consider S2 cell covering for the
surge pricing zone problem — surge zones are often arbitrary polygons, and S2 covering
gives you a minimal set of cells without manual boundary tuning. The tradeoff is S2
requires a C++ or Java library; if you're running Go microservices you add a CGo bridge.
At Uber's scale the quadtree approach in a co-located cache (one per city shard) makes
sense for the passenger-facing read path, with geohash Redis for the write path. Also:
geohash precision 6 cells are 1.2km × 0.6km, which is non-square — at the equator that
is fine but at high latitudes the cells become increasingly distorted. S2 corrects for
this projection distortion."

### 2.6 Part 2 Brainstorming Q&A

**Q: Why is the geohash cell non-square (1.2km × 0.6km) instead of square?**

Geohash alternates between bisecting longitude and latitude. Longitude spans 360 degrees,
latitude spans 180 degrees — a 2:1 ratio. When you alternate the bisections, longitude
gets one more bisection than latitude for odd-length hashes, making cells twice as wide
as tall. For even-length hashes, the ratio reverses. At precision 6 (even length), cells
are actually about 1.2 km wide (longitude) and 0.6 km tall (latitude). This matters for
your radius calculation: a geohash-6 prefix scan for a 2 km radius query will not cover
a uniform circle — it covers a rectangle, and the radius may extend beyond the cell in
the latitude direction. This is another reason you must always check neighboring cells
and filter by actual Haversine distance afterward.

**Q: Can you explain why S2's Hilbert curve is better than geohash's Z-order curve?**

Geohash implicitly uses a Z-order curve (also called a Morton code), which maps 2D to
1D by interleaving the bits of the x and y coordinates. The Z-order curve mostly
preserves locality — nearby 2D points tend to have similar 1D values — but it has
discontinuities at cell boundaries, particularly at the "Z" jump points where the curve
reverses direction. Two points very close in 2D space can be far apart on the Z-order
1D mapping if they happen to straddle one of these jump points. The Hilbert curve fills
space in a smoother pattern (no sharp direction reversals), so discontinuities are rarer
and smaller. In practice for the driver location use case, the difference is marginal —
the boundary problem fix (checking 9 cells) effectively compensates for geohash's
discontinuities. The Hilbert curve matters more for complex shape covering (like surge
zones) where S2's cell covering algorithm can represent an arbitrary polygon with fewer
cells than an equivalent geohash-based approach.

**Q: At what point does a quadtree outperform geohash in a real system?**

The crossover point is when driver density varies by more than 1000x across your service
area. In a geohash-6 grid, a cell in Manhattan might contain 500 drivers while a cell
in rural Kansas contains 0 drivers. If you're doing Uber's ride matching, you're scanning
many empty cells in sparse regions — wasted I/O. A quadtree's adaptive subdivision means
rural Kansas gets represented by a single large cell (fast lookup, no wasted scans) while
Manhattan is subdivided into many small cells (precise, low false positives). But in
practice, Uber's production system uses a hybrid: geohash for the distributed Redis
storage layer (easy sharding), and quadtrees within individual city-level services that
serve the matching hot path. Quadtrees win on read efficiency; geohash wins on write
distribution. If your system is read-heavy (like searching for restaurants on DoorDash,
not real-time driver tracking), the quadtree's read advantage may matter more.

---

## Part 3: Driver Location Service — The Write Path at Scale

### 3.1 The Problem Statement

You have 5 million active drivers globally. Each sends a GPS update every 4 seconds.
That is 1.25 million writes per second. Each write must:
1. Update the driver's current location in the proximity index (so passengers can find them)
2. Persist the location to a time-series store (for ETA model training, trip replay, fraud detection)
3. Trigger a push to any passenger who is actively tracking this driver's movement

This is one of the highest write-throughput systems you will encounter in an interview.
It has to be faster and more available than your typical database write — the system
must absorb traffic spikes (New Year's Eve in a city could triple normal driver density)
and degrade gracefully rather than dropping updates.

### 3.2 Architecture: Write Path

```
ASCII DIAGRAM: DRIVER LOCATION UPDATE PIPELINE

Driver App (iOS/Android)
         │
         │  GPS coordinates every 4 seconds
         │  (lat, lng, bearing, speed, accuracy, timestamp)
         ↓
[Load Balancer / API Gateway]
         │
         ↓
[Location Ingestion Service]  ←── horizontal, 100+ instances
    (gRPC or WebSocket)            each handles ~12,500 drivers
         │
         ├──────────────────────────────────────────┐
         │                                          │
         ↓                                          ↓
[Kafka Cluster]                            [Redis Cluster]
 Topic: driver-locations                    GeoSets: driver positions
 Partitioned by driver_id % N               Sharded by geohash prefix
         │                                  TTL: 30 seconds per driver
         │
    ┌────┴────────────────────────────────────────┐
    │                                             │
    ↓                                             ↓
[Location History Writer]              [Passenger Notification Fan-out]
 Cassandra / Bigtable                   Pub/Sub per trip_id
 Row key: driver_id + timestamp         Pushes to passenger app
 Retention: 30 days                     (if active trip in progress)
```

### 3.3 The Ingestion Layer: WebSocket vs gRPC

The driver app needs a persistent connection to the server so it can stream location
updates without the overhead of a new HTTP handshake every 4 seconds. Two options:

**WebSocket:** Browser-compatible, widely supported, bidirectional. Each connection is
a long-lived TCP connection. Works well for mobile apps. The main challenge is that a
single WebSocket server can handle roughly 100,000–200,000 concurrent connections before
memory becomes the bottleneck (each connection requires OS file descriptor + buffer
memory). With 5 million concurrent drivers, you need 25–50 WebSocket gateway servers
just for connection handling.

**gRPC Streaming:** More efficient than WebSocket for high-frequency binary data.
gRPC uses HTTP/2 multiplexing so multiple streams share a single TCP connection (matters
for multiplexed channels from fleet management servers). The binary Protocol Buffer
serialization is smaller than JSON. Uber uses gRPC for server-to-server communication
and has used it for the driver app as well.

**Practical choice:** Either works. WebSocket is easier to explain in an interview.
gRPC with streaming is more efficient in production.

### 3.4 Redis GeoSet: The Core Spatial Store

Redis has a native GeoSet data type — it is actually a sorted set where the score is a
52-bit geohash of (longitude, latitude). This gives roughly 0.6m precision globally.

Key Redis commands for the driver location use case:

```
# Driver sends update: GEOADD adds (lng, lat, member) to the set
GEOADD drivers:city:nyc  -73.9857 40.7484  driver_12345

# Find drivers within 2km of passenger at (-73.98, 40.75):
GEORADIUS drivers:city:nyc  -73.98 40.75  2 km  WITHCOORD WITHDIST ASC COUNT 20

# Get a single driver's current position:
GEOPOS drivers:city:nyc  driver_12345

# Driver goes offline — delete their entry:
ZREM drivers:city:nyc  driver_12345
```

Redis executes GEORADIUS in O(N + log(M)) where N is the number of elements in the
result and M is the total set size. For a 2km radius query in a city with 50,000 drivers,
this runs in under 1 millisecond.

### 3.5 Sharding Redis

One Redis instance cannot handle 1.25M writes/second. Redis is single-threaded for
write operations (its concurrency comes from event loop I/O multiplexing, not parallelism).
A single Redis instance can handle roughly 100,000–200,000 simple operations per second
on commodity hardware.

**Sharding Strategy: By Geographic Region**

The natural sharding key is geographic. You partition the world into regions (Uber uses
"geo cells" — essentially large geohash prefixes) and assign each region to a Redis
shard. All drivers in New York City are in one set of shards; all drivers in Los Angeles
are in another.

This works because proximity queries are always local. A passenger in NYC never asks
"find me the closest driver in LA." So a proximity query always hits exactly one regional
shard.

```
REDIS SHARDING BY REGION:

drivers:region:nyc    → Redis Shard 1 (NYC, NJ, CT drivers)
drivers:region:sf     → Redis Shard 2 (Bay Area drivers)
drivers:region:la     → Redis Shard 3 (LA, OC drivers)
drivers:region:chi    → Redis Shard 4 (Chicago drivers)
...
drivers:region:lon    → Redis Shard 20 (London drivers)
drivers:region:ams    → Redis Shard 21 (Amsterdam drivers)

Each shard handles ~200K-500K drivers.
Each shard = Redis primary + 1-2 replicas.

Write path: location update → look up driver's current region
            → GEOADD to correct shard

Edge case: driver crosses region boundary
→ ZREM from old shard, GEOADD to new shard
→ Detected by comparing old geohash prefix to new
```

### 3.6 Cassandra for Location History

Redis stores only the current location (with 30-second TTL). For historical location
data — needed for ETA model training, trip replay, and fraud detection — you write to
Cassandra.

**Cassandra Schema for Location History:**

```
CREATE TABLE driver_locations (
    driver_id   UUID,
    timestamp   TIMESTAMP,
    lat         DOUBLE,
    lng         DOUBLE,
    speed       FLOAT,
    bearing     FLOAT,
    accuracy    FLOAT,
    trip_id     UUID,        -- null if not on a trip
    PRIMARY KEY (driver_id, timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC)
  AND default_time_to_live = 2592000;   -- 30 days TTL
```

Cassandra is ideal here because:
- Write-optimized (LSM tree, appends to memtable, no random writes)
- Time-series data is a natural fit for its clustering column model
- Automatic TTL handles data expiration without separate cleanup jobs
- Linear horizontal scalability — add nodes to handle more write throughput

At 1.25M location writes/second × 30 days retention × ~100 bytes per record, the raw
storage requirement is about 324 TB. Cassandra clusters at this scale are not unusual
at Uber.

### 3.7 The Fan-Out Problem: Live Trip Tracking

When a passenger is watching their driver approach on the map, the passenger app needs
to receive the driver's location every 2-4 seconds. This is a publish-subscribe problem.

**Naive approach:** passenger app polls the location service every 4 seconds. Simple,
but at 500,000 active trips, that is 125,000 poll requests per second hitting the location
service for trip tracking alone — on top of the 1.25M driver update writes. This is
wasteful; most polls return "no significant change."

**Better approach:** publish-subscribe per trip. When a trip starts, the trip service
creates a Pub/Sub channel keyed by trip_id. The location service subscribes to the
relevant driver's updates and publishes them to this channel. The passenger's app server
subscribes to this channel and pushes updates over a WebSocket connection to the passenger.
No polling — the update propagates only when a new location arrives.

```
TRIP TRACKING PUB/SUB:

Driver App → Location Service → [Kafka topic: driver-locations]
                                         │
                                    [Trip Tracker]
                                    subscribes to
                                    driver_12345's updates
                                         │
                                    [Pub/Sub channel: trip:trip_abc]
                                         │
                                    [Passenger Server]
                                         │ WebSocket push
                                    Passenger App
```

### 3.8 Intern → Staff: Location Service

**Intern:** "Store driver location in a database, passenger polls every 5 seconds."
(No awareness of write scale, polling is wasteful.)

**Junior (L3):** "Use Redis to store current location, Redis is fast." (Right technology,
no sharding strategy, no thought about Cassandra for history.)

**Mid-Level (L4):** "Redis GeoSets for current location, sharded by city. Cassandra for
history. But how do I handle the WebSocket connection layer?"

**Senior (L5):** "Kafka for ingestion buffer at the front (absorbs spikes), location
service workers consume from Kafka and write to Redis + Cassandra. Redis sharded by
geohash-2 prefix. Trip tracking via Pub/Sub. Heartbeat-based offline detection with
30-second threshold."

**Staff (L6):** "A few things the L5 answer misses. First: Kafka partitioning by driver_id
ensures all updates for a driver go to the same consumer, preventing out-of-order updates
to Redis. Second: at 1.25M/sec, even Kafka needs sizing — 100+ partitions, 10+ brokers,
with replication factor 3. Third: the Cassandra write path should be async (fire and
forget from the location service's perspective) with a dead-letter queue for failed writes.
Fourth: Redis GeoSets GEORADIUS was deprecated in Redis 6.2 in favor of GEOSEARCH — if
you say GEORADIUS an interviewer at Redis Labs will notice. Fifth: driver region changes
(crossing shard boundaries) need a distributed transaction or at-least-once semantics with
deduplication — you cannot afford a driver to disappear from both shards simultaneously."

### 3.9 Brainstorming Q&A

**Q: Why use Kafka between the app and Redis? Why not write directly to Redis?**

Kafka serves as a durable buffer and backpressure mechanism. Without Kafka, if Redis
is slow (e.g., during a resharding event or a GC pause on the Redis proxy), the driver
apps would start getting write errors. The driver app would have to implement retry logic,
and you might lose location updates. With Kafka in front, the driver app writes to Kafka
(which is extremely fast — Kafka can sustain millions of writes/second on commodity
hardware with sequential disk writes). The Kafka consumer writes to Redis at a rate Redis
can absorb. If Redis slows down, the Kafka lag grows but no updates are lost — they are
durably stored in Kafka for up to the configured retention period. This decoupling is the
key operational benefit. It also means you can add new consumers (like the trip tracker
or the ETA model trainer) without modifying the driver app at all.

**Q: Why not use a time-series database like InfluxDB or TimescaleDB instead of Cassandra
for location history?**

A purpose-built time-series database like InfluxDB or TimescaleDB would actually work
well for the location history use case — they have better compression for time-series
data and sometimes faster queries for time-range scans on a single driver. The reason
Uber and similar companies tend to use Cassandra is operational familiarity and the
fact that Cassandra already exists in their stack for other use cases (like trip data,
user data). Running one database technology at massive scale is generally safer than
running two specialized databases. That said, if you were designing this from scratch
today, InfluxDB or even Apache Druid might be worth evaluating. In an interview, the
right answer is "Cassandra is a solid choice here, but I'd also evaluate InfluxDB for
the time-series characteristics — the tradeoff is operational complexity vs. storage
efficiency." Showing you know both options and can reason about the tradeoff is what
matters.

**Q: How do you handle the case where a driver's GPS accuracy is poor (e.g., in a tunnel
or urban canyon with tall buildings)?**

GPS accuracy degrades significantly in tunnels and dense urban areas. The driver app
includes an accuracy field in each location update — this is the radius of uncertainty
in meters. The location service should filter out updates with accuracy worse than a
threshold (e.g., > 50 meters) or use a Kalman filter to smooth the path. A Kalman filter
combines the last known position, speed, and bearing with the new GPS reading to produce
a smoothed estimate. This matters for passenger experience — if you show a driver's icon
jumping around on the map due to poor GPS, passengers get confused. The map rendering
layer often applies its own Kalman filter or spline interpolation between received updates
so the driver icon appears to move smoothly. For the storage layer, you might store both
the raw GPS reading and the Kalman-filtered position, so engineers can debug GPS quality
issues later.

---

## Part 4: Proximity Search — Finding Drivers Within 2km

### 4.1 The Query

A passenger opens the Uber app. Their phone sends their coordinates to Uber's servers.
The server must return a list of nearby available drivers — ideally within 100 milliseconds.
This is the proximity search problem.

The query: "Find all drivers in AVAILABLE state within R kilometers of point (lat, lng),
sorted by distance, return the closest K."

### 4.2 Approach 1: Geohash Prefix Range Scan

**Step 1:** Encode the passenger's location as a geohash at the appropriate precision.
For a 2km search radius, precision 6 is the right choice (cells are ~1.2km × 0.6km —
smaller than the search radius so you only need to check a few cells).

**Step 2:** Fetch all drivers in the target geohash cell. In Redis: `ZRANGEBYLEX drivers:nyc [9q8yym [9q8yyn` (all members with the target geohash prefix).

**Step 3:** Also fetch all drivers in the 8 neighboring cells (boundary problem fix).

**Step 4:** For all returned drivers (~50–500 in a dense city), compute the actual
Haversine distance to the passenger. Filter those beyond 2km.

**Step 5:** Sort by distance, return top K.

**Haversine Distance Formula**

The Haversine formula computes the great-circle distance between two points on a sphere:

```
a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlng/2)
c = 2 × atan2(√a, √(1-a))
d = R × c    (R = 6,371 km, Earth's radius)
```

This is accurate to within 0.5% for distances under 1000 km. For Uber's short distances
(2–5 km), even simpler approximations work fine (treat the Earth as flat locally). In
Python, `geopy.distance.distance()` or the Redis GEORADIUS command handles this for you.

### 4.3 Approach 2: Redis GEOSEARCH (Modern API)

Redis 6.2 added GEOSEARCH which supersedes GEORADIUS:

```redis
GEOSEARCH drivers:nyc
  FROMLONLAT -73.98 40.75
  BYRADIUS 2 km
  ASC
  COUNT 20
  WITHCOORD WITHDIST
```

This single Redis command handles the geohash encoding, neighboring cell expansion, and
Haversine filtering internally. It returns the 20 closest drivers within 2km, sorted by
distance. Latency: < 1 ms for a set of 50,000 drivers.

### 4.4 The Sparse Area Problem — Radius Expansion

In rural areas, there might be zero drivers within 2km. Uber's app shows "no drivers
available" only after checking a wider area. The fix: adaptive radius expansion.

```
RADIUS EXPANSION ALGORITHM:

1. Query radius = 2km
2. If results < MIN_DRIVERS (say, 3):
   radius = radius × 1.5  (3km)
3. If results < MIN_DRIVERS:
   radius = radius × 1.5  (4.5km)
4. Continue expanding up to MAX_RADIUS (e.g., 15km)
5. If still no results: show "no drivers in your area"

For geohash, expansion means dropping one character of precision:
"9q8yym" (precision 6, 1.2km) → "9q8yy" (precision 5, 4.9km)
→ "9q8y" (precision 4, 39km)
```

This adaptive expansion is especially important for DoorDash and food delivery, where
you might want to show restaurants within 5km, but in suburban areas need to expand to
15km to show enough options.

### 4.5 Surge Pricing Zones and Irregular Shapes

Surge pricing is not applied to a circular radius — it applies to geographic zones like
"downtown San Francisco" or "SFO airport pickup zone." These are polygons, not circles.

**Approach for polygon-shaped zones:**

1. **Geohash approach:** Enumerate all geohash cells that intersect the polygon. For a
surge zone, Uber precomputes the set of geohash cells that are "inside" the zone and
stores this as a lookup table. When a driver's location update arrives, check if their
geohash is in the surge zone set. O(1) lookup.

2. **S2 approach:** Use S2's cell covering to compute the minimal set of S2 cells that
cover the polygon. This gives a cleaner covering with fewer cells and less false-positive
area outside the polygon.

3. **Point-in-polygon check:** For small zones with high accuracy requirements, compute
whether a point is inside a polygon using the ray-casting algorithm. More accurate but
more expensive.

```
SURGE ZONE COVERAGE (S2 APPROACH):

Polygon outline of "Downtown SF Surge Zone":
        *---------*
       /           \
      *             *
      |             |
      *    SURGE    *
       \           /
        *---------*

S2 Cell Covering (Level 12 cells, ~2km² each):
+----+----+----+
|    | XX | XX |    XX = cells fully inside zone
+----+----+----+    X  = cells partially covering zone
| XX | XX | XX |       (include these too; filter at driver level)
+----+----+----+
|    | XX |    |
+----+----+----+

Surge zone stored as: Set{cell_A, cell_B, cell_C, cell_D, cell_E, cell_F}
Driver update: check if driver's S2 cell is in this set → O(1)
```

### 4.6 Intern → Staff: Proximity Search

**Intern:** "SQL query with BETWEEN clauses on lat and lng."
(O(N) scan, won't scale.)

**Junior (L3):** "Geohash, prefix scan in Redis."
(Right idea, misses boundary problem and sparse area handling.)

**Mid-Level (L4):** "Geohash prefix scan + 8 neighbors + Haversine filter. Redis GEOSEARCH."
(Correct and complete for the basic case.)

**Senior (L5):** "Add adaptive radius expansion for sparse areas. Handle surge zone
queries with precomputed geohash sets per zone. Consider S2 for complex zone shapes."

**Staff (L6):** "The precision choice matters: geohash-6 at 1.2km cell size means a 2km
radius query touches at most 9 cells — that's the right precision. At geohash-5 (4.9km
cells) you'd be scanning too much area (too many false positives); at geohash-7 (153m
cells) you'd need to expand to hundreds of cells for a 2km radius. The precision should
be chosen so the search radius spans 1–3 cell widths. Also: for Uber's matching algorithm,
distance is not the only sort key — driver acceptance rate, driver rating, and estimated
time to pickup (not just straight-line distance) all factor in. The proximity search
returns candidates; the matching service applies the business logic ranking. Keep these
separate."

### 4.7 Brainstorming Q&A

**Q: If Redis is in-memory, what happens if the Redis instance crashes and we lose all
driver locations?**

Redis is designed for exactly this recovery scenario. First, Redis replication: every
Redis primary has 1-2 replicas. If the primary crashes, Redis Sentinel or Redis Cluster
automatically fails over to a replica within a few seconds. During those seconds, driver
location updates are buffered in Kafka — the location service consumers simply wait for
Redis to recover before writing. Second, even if both primary and replica fail
simultaneously (unlikely but possible), recovery is fast: within 30–60 seconds, all
5 million active drivers will have sent 7–15 new location updates, repopulating Redis
from their own heartbeats. You do not need Redis persistence (AOF or RDB snapshots) for
the driver location use case because the data is ephemeral — it expires in 30 seconds
anyway. This is an important insight: when data is short-lived and regenerates quickly,
you can sacrifice durability for speed.

**Q: How does the matching service actually select which driver to offer a trip to?**

Proximity is necessary but not sufficient. The matching service at Uber runs a continuous
loop (every few seconds) that assigns available trips to available drivers in a region.
It uses a weighted scoring function that considers: distance from driver to pickup (lower
is better), driver acceptance rate (drivers who frequently decline get deprioritized to
reduce wait times), driver rating, and sometimes driver-passenger language or preference
matching. More sophisticated systems use optimization algorithms — Uber's H3-based
hexagonal market is actually solved as a bipartite matching problem, maximizing total
value (minimizing total pickup time) across all open trips and available drivers in a
market simultaneously. This is a linear programming problem, solved with auction-based
algorithms at Uber's Marketplace team. For the interview, mentioning that proximity
search returns candidates and a separate matching service applies business logic is the
right level of detail.

**Q: How do you prevent showing a driver to multiple passengers simultaneously?**

This is a race condition problem. If 100 passengers are searching for drivers simultaneously,
multiple passengers might see the same driver and all try to request them at once. The
solution is two-phase matching: the proximity search returns candidate drivers without
reserving them. When a passenger requests a trip, the matching service attempts to
atomically lock a driver (using a Redis SET NX with a short TTL, or a distributed lock).
If the lock succeeds, that driver is assigned to that passenger. If the lock fails
(another passenger got there first), the matching service picks the next candidate.
This optimistic concurrency approach avoids database-level locks in the proximity
search hot path while still preventing double-assignment.

---

## Part 5: Road Network Representation

### 5.1 OpenStreetMap — The World's Road Graph

Routing (find the fastest way from A to B) requires a model of the road network.
Google built its own from scratch over decades of mapping. Every other routing system —
Uber, Apple Maps, HERE, TomTom — either licenses proprietary map data or uses
OpenStreetMap (OSM), the open-source community-maintained global map.

**OSM Data Model:**

- **Nodes:** Points on the Earth's surface. Every intersection, every point along a curve
  in a road. OSM has about 8 billion nodes total globally, of which ~100 million are
  intersections (graph vertices).
  
- **Ways:** Ordered sequences of nodes forming a line. Road segments are "ways." A way
  has attributes: road type (highway, residential, footpath), max speed, name, one-way
  or bidirectional.
  
- **Relations:** Groups of ways forming complex objects (a route, a restriction like
  "no left turn from Main St to 1st Ave").

**The Road Graph**

For routing purposes, OSM is converted into a directed weighted graph:
- **Nodes (vertices):** Intersections only (not every curve point)
- **Edges:** Road segments between intersections, with weights = travel time in seconds
- **Directed:** One-way streets are represented as directed edges (A→B exists, B→A does not)
- **Turn restrictions:** "No left turn" is represented by removing the corresponding edge

```
ASCII DIAGRAM: ROAD NETWORK GRAPH

OSM Raw Data:              Graph Model:
                           
  A---B---C                A→B (30 sec), A←B (30 sec)
  |       |                B→C (45 sec), B←C (45 sec)
  D---E---F                A→D (60 sec), A←D (60 sec)
                           D→E (30 sec), D←E (30 sec)
  Note: B→C is                      ... etc.
  one-way (one-way street)
                           One-way: B→C exists, C→B REMOVED
  A---B--→C                
  |       |                Turn restriction: "no right turn B→C→F"
  D---E---F                Edge B→C, C→F flagged as restricted

WEIGHTED GRAPH:

    [A]---30s---[B]---45s---[C]
     |                      |
    60s                    30s
     |                      |
    [D]---30s---[E]---25s---[F]

Dijkstra from A to F:
A→D (60) → D→E (30) → E→F (25) = 115 seconds ✓
A→B (30) → B→C (45) → C→F (30) = 105 seconds ✓ (faster!)
```

### 5.2 Edge Weights — Travel Time vs. Distance

The graph's edge weights are not physical distance in meters — they are estimated travel
time in seconds. This is a crucial distinction. A 1-mile freeway segment at 65mph takes
55 seconds. A 1-mile downtown segment with stoplights at 15mph takes 240 seconds.

Edge weights in a production routing graph have multiple components:

1. **Base weight:** Distance ÷ speed limit (best-case travel time)
2. **Road type modifier:** Highways are preferred over residential streets (lower penalty)
3. **Turn costs:** Left turns take longer than right turns (especially in USA where left
   turns cross oncoming traffic). Turn costs are 10–30 seconds in urban areas.
4. **Time-of-day factor:** Rush hour weights are multiplied by a slowdown factor (1.5x–3x)
5. **Real-time traffic:** Current speed on this segment from GPS probe data

### 5.3 The Scale Problem

Full planet OSM graph: ~100M nodes, ~1B edges. Uncompressed, this is hundreds of
gigabytes. Running Dijkstra's shortest path algorithm on this graph naively — starting
from your origin, exploring nodes in order of increasing distance until you reach the
destination — would take minutes. Google Maps answers in milliseconds.

The gap: Dijkstra on a 1-billion-edge graph explores millions of nodes. Google Maps
needs to explore thousands. This requires algorithmic preprocessing, which we cover in
Part 6.

### 5.4 Brainstorming Q&A

**Q: How does the routing graph handle roads that don't exist yet or temporary road
closures?**

Real-time map changes — a road closed for construction, a new road opened — need to
propagate quickly. For permanent changes (a new highway opens), the full road graph is
re-preprocessed on a regular schedule (daily or weekly, depending on the routing system).
For temporary changes (road closed due to accident, a detour), the routing system uses
a "live traffic" overlay: a separate layer of edge weight modifications and blocked edges
that is applied on top of the base graph at query time. The base precomputed graph stays
unchanged; the live overlay modifies edge weights for affected segments. This is much
faster than re-preprocessing the whole graph. Google Maps uses a similar approach —
the precomputed Contraction Hierarchy handles the base graph, and real-time incidents
modify specific edges' weights at query time.

**Q: How do you represent highway on-ramps and interchanges, which are complex 3D
structures?**

Grade-separated intersections (where one road passes over another without intersecting)
are the bane of road graph representation. OSM handles this by tagging nodes with
layer attributes — a node on an overpass bridge has `layer=1` while the road below has
`layer=0`. The routing graph treats these as disconnected: you cannot turn from the
bridge to the road below unless there is an on-ramp or off-ramp node. Highway
interchanges (like a cloverleaf) are represented by explicit loop roads — the on-ramp
and off-ramp segments are real OSM ways with their own nodes. This is why "map data"
for routing is not just geographic coordinates — it is a rich semantic graph with
hundreds of attributes per edge.

---

## Part 6: Routing Algorithms — From Dijkstra to Contraction Hierarchies

### 6.1 Dijkstra's Algorithm

Dijkstra's algorithm finds the shortest path from a source node to all other nodes in
a weighted graph. It works by maintaining a priority queue of nodes sorted by their
tentative distance from the source.

```
DIJKSTRA PSEUDOCODE:

dist[source] = 0
dist[all others] = ∞
priority_queue = {(0, source)}

while queue not empty:
    (d, u) = queue.pop_min()
    if d > dist[u]: continue  # stale entry
    for each neighbor v of u:
        new_dist = dist[u] + weight(u, v)
        if new_dist < dist[v]:
            dist[v] = new_dist
            queue.push((new_dist, v))

return dist[destination]
```

**Performance:** O((V + E) log V) where V = nodes, E = edges.

On a 100M-node, 1B-edge graph: roughly 10^9 × log(10^8) ≈ 2.7 × 10^10 operations.
At 10^9 operations/second, that is 27 seconds per query. Far too slow.

### 6.2 A* — Adding a Heuristic

A* improves on Dijkstra by using a heuristic to prioritize promising paths. Instead of
exploring nodes in order of their distance from the source, A* prioritizes nodes by
their distance from the source PLUS an estimated distance to the destination.

The heuristic for geographic routing: the straight-line (Euclidean/Haversine) distance
from the current node to the destination. Since you cannot travel faster than the speed
limit, and you cannot travel in a straight line on a real road, the true remaining travel
time is always ≥ straight-line distance ÷ max speed. This is called an "admissible
heuristic" — it never overestimates, so A* is guaranteed to find the optimal path.

A* reduces the number of nodes explored by 10–100× compared to Dijkstra on road networks.
But on a planet-scale graph (SF to NYC), even A* explores millions of nodes. Not fast
enough for real-time queries.

### 6.3 Contraction Hierarchies — The Production Solution

Contraction Hierarchies (CH) is the algorithm used by OSRM (Open Source Routing Machine),
GraphHopper, and (a variant of) Google Maps. It achieves sub-millisecond queries on
planet-scale graphs through offline preprocessing.

**The Core Idea: Shortcuts**

Imagine a highway with 100 intermediate nodes (intersections along the highway). Any
route from city A to city B that uses this highway passes through all 100 nodes. During
preprocessing, CH "contracts" the intermediate nodes — it removes them from the graph
and replaces them with a single "shortcut" edge from the highway entrance to the exit
with the correct cumulative weight.

```
BEFORE CONTRACTION:

A→n1→n2→n3→n4→n5→n6→n7→n8→n9→n10→B
 (each edge = 30 seconds, 10 intermediate nodes)

AFTER CONTRACTING n1 through n9:

A ──────────────────────────────→ B
        weight = 330 seconds (30 × 11)

One edge replaces 10. Query time: 1 hop instead of 11.
```

**The Hierarchy**

CH assigns an "importance" level to each node based on how many shortcuts would need to
be added to contract it. Major highway junctions are high-importance (many shortcuts).
Small residential intersections are low-importance.

Preprocessing contracts nodes from lowest to highest importance, adding shortcut edges
as needed. The result is a layered graph: minor streets at the bottom, major arterials
in the middle, highways at the top.

**Bidirectional Search**

CH queries run bidirectional Dijkstra: simultaneously expand forward from the source
AND backward from the destination, but only allowing the search to "go up" the hierarchy
(to higher-importance nodes). The two searches meet at a high-importance node (typically
a major highway junction).

```
ASCII DIAGRAM: CONTRACTION HIERARCHY QUERY

Source: San Francisco (local street)
Destination: Los Angeles (local street)

Hierarchy levels:
Level 3: ★ Major interstate interchanges (I-5/I-580, I-5/SR-14)
Level 2: ▲ Highway on/off ramps
Level 1: • Major arterials
Level 0: · Local streets

FORWARD SEARCH (from SF):          BACKWARD SEARCH (from LA):
· → · → • → ▲ → ★                ★ ← ▲ ← • ← · ← ·
         ↑                            ↑
         Expands up hierarchy only    Expands up hierarchy only

MEETING POINT: ★ (major interstate junction, e.g., I-5/I-405 in SoCal)

WITHOUT CH: explore millions of nodes across entire western US
WITH CH: explore a few thousand nodes up to the highest-level shortcut

Query time: < 1 ms (vs. 27 seconds for naive Dijkstra)
```

**Preprocessing Cost**

CH preprocessing on the full planet OSM graph takes roughly 1–3 days on a powerful
multi-core server. The result is a precomputed shortcut graph that is much larger than
the original (more edges, due to shortcuts) but enables sub-millisecond queries.
Preprocessing is done offline, updated periodically (weekly for major road changes).

**When Preprocessing Becomes Stale**

If a major road closes (natural disaster, infrastructure failure), the precomputed CH
graph becomes incorrect. For real-time incidents, production systems use a two-layer
approach: CH for the base graph, live traffic overlay at query time. The overlay can
increase edge weights (slow down) or block edges entirely, and the bidirectional CH
search respects these overrides.

### 6.4 Other Routing Optimizations

**Transit routing:** For public transit (subway + bus), the road graph model does not
apply. Transit routing uses RAPTOR (Round-Based Public Transit Optimized Router), which
works on transit schedules and handles transfers.

**Multi-modal routing:** Walk to subway, ride subway, walk to destination. Requires
combining transit and walking graphs. Google Maps does this — Uber generally does not
(cars only, mostly).

**Alternative routes:** Users often want 2–3 route options, not just the single fastest.
Generating "sufficiently different" alternatives (not just minor variations of the same
path) is a research problem. One approach: find the shortest path, remove its edges,
find the next shortest path, check if it is sufficiently different.

### 6.5 Intern → Staff: Routing Algorithms

**Intern:** "Run Dijkstra on the road network."
(Correct algorithm, completely infeasible at scale.)

**Junior (L3):** "Use A* with a Haversine heuristic to speed it up."
(Better, but still not fast enough for planet-scale.)

**Mid-Level (L4):** "Precompute the graph offline, use Contraction Hierarchies.
Queries run in < 1ms." (Right answer, but can they explain why?)

**Senior (L5):** "CH preprocessing contracts low-importance nodes, adds shortcuts.
Query runs bidirectional Dijkstra only going up the hierarchy. Stale preprocessing
handled by live traffic overlay at query time. Full planet CH takes 1–3 days to build."

**Staff (L6):** "A few nuances. First: CH gives you the shortest path, but for Uber you
want the fastest path given current traffic. You'd use time-dependent edge weights and
a variant called TCH (Time-expanded Contraction Hierarchies) or run CH with real-time
traffic overlays. Second: CH is not great for rerouting mid-trip — if a road closes
while you're driving, you want to re-route quickly. Uber uses a simpler algorithm for
re-routing (local Dijkstra from current position) because the re-routing area is small.
CH is overkill for local re-routing. Third: the shortcut graph is much larger than the
original (3–5× more edges). Memory is a concern for per-continent shards — a full planet
CH graph may require 100+ GB of RAM per routing server, which is why routing is sharded
by continent or region."

### 6.6 Brainstorming Q&A

**Q: How does Google Maps provide turn-by-turn instructions, not just a path?**

Computing the path (which edges to traverse) is separate from generating the instructions.
Once you have the path — an ordered list of edges — you analyze each junction to determine
the instruction: "Turn left onto Market St," "Stay on I-101 North," "Take exit 42A."

This requires the road graph to have additional semantic information beyond just weights:
road names, turn angles (computed from the incoming and outgoing edge vectors), exit
numbers, and road classifications. At each junction, the routing system computes the
relative angle between the current road segment and the next (0° = straight, -90° = left,
+90° = right). Then it generates text: anything within ±15° is "continue straight,"
-15° to -75° is "turn left," etc. Complex interchanges generate "take the ramp" or
"keep left" instructions based on the road type tags. The text-to-speech system then
reads these instructions. Localization (translating "Turn left" into 50+ languages)
and street name pronunciation are additional engineering challenges.

**Q: How does Google Maps handle route computation for bicycles vs. walking vs. driving?**

The road graph has edge tags for allowed transportation modes. A footpath edge is walkable
but not drivable; a highway edge is drivable but not walkable. When computing a cycling
route, the routing system loads a different set of edge weights (bike speed = ~15 km/h,
penalize high-grade hills, prefer designated bike lanes) and uses only edges accessible
to cyclists. Each transportation mode essentially uses a different "view" of the same
underlying OSM graph. CH preprocessing is done separately for each mode, since the
contracted nodes and shortcuts differ (a shortcut that skips a highway is valid for
cars but not cyclists). This is why Google Maps can switch between modes quickly — the
preprocessing is done offline for all modes simultaneously.

---

## Part 7: ETA Prediction

### 7.1 Why "Distance ÷ Speed Limit" Is Wrong

Imagine Google Maps estimates your route is 20 miles on I-101 with a speed limit of
65 mph. Naively: 20 miles ÷ 65 mph = 18.5 minutes. But it is Friday at 5 PM and I-101
is a parking lot. The actual travel time is 55 minutes.

ETA prediction is a machine learning problem. The road network gives you the route;
ETA tells you when you will arrive.

### 7.2 Data Sources for ETA

**1. Historical Travel Times**

Every GPS trace from every phone that has driven on a road segment becomes training data.
Google Maps has access to billions of GPS traces. For each road segment, you can compute
the average travel time at each hour of each day of the week. Monday 8–9 AM on this
segment has historically taken 4.2 minutes; Monday 3–4 PM has taken 1.8 minutes.

This historical data is pre-aggregated by (segment_id, day_of_week, hour_of_day) and
stored in a lookup table. At routing time, you look up the expected travel time for each
segment based on the current time.

**2. Real-Time Traffic Probe Data**

Every phone navigating with Google Maps or Uber sends its current speed back to the
server. These "probe" measurements tell you: right now, on this segment, cars are moving
at 12 km/h (instead of the 65 km/h speed limit). This is how Google Maps shows "slow"
or "heavy traffic" in real-time.

The challenge: you need enough probes per segment to get a reliable speed estimate.
A segment with 2 probes might have noisy data; a segment with 200 probes gives a
reliable average. In practice, major highways get thousands of probes per minute; quiet
residential streets might get 1 probe per hour.

**3. Third-Party Traffic Data**

Some traffic providers (INRIX, TomTom) sell historical and real-time traffic data based
on aggregated GPS data from many sources (fleet vehicles, navigation systems). Google
also uses information from its Maps SDK embedded in many third-party apps.

### 7.3 The ETA Model

A production ETA model combines multiple signals:

```
ETA = f(route, time_of_day, day_of_week, weather, events, real_time_probes)

Features:
- For each segment on the route:
  - segment_id → historical_avg_time[day_of_week][hour]
  - segment_id → current_probe_speed (from last 5 minutes of GPS data)
  - segment_length
  - road_type (highway, arterial, residential)
- Global features:
  - current weather (rain → 1.2× slowdown)
  - nearby events (concerts, sports games → surge near venue)
  - time to nearest school zone hours
  - holidays

Model: gradient boosted trees or neural network
Output: predicted travel time in seconds (+ confidence interval)
```

**ETA as a Distribution**

ETA should not be a single number — it should be a distribution. "You will arrive in
8 minutes (p50) to 14 minutes (p90)" gives users better information than "8 minutes."
Some production systems output the p50 (median) for the displayed ETA and use the p90
internally for scheduling (e.g., telling a driver to pick up a passenger by a certain
time that accounts for uncertainty).

### 7.4 The Uber ETA Bug (Real Incident)

In 2019, Uber's ETA model consistently underestimated airport pickup times by 30–40%
at major airports like SFO, LAX, and O'Hare. The root cause: the model calculated ETA
as time from the driver's current location to the airport entrance. But arriving at the
airport entrance is not the same as completing the pickup — passengers at airports are
at specific terminals, often 0.5–1.5 miles from the airport entrance. Terminal access
roads and parking structures added 8–15 minutes to the actual pickup time.

The model had been trained on city pickups where the destination point and the actual
pickup location are essentially the same. Airports broke this assumption.

The fix: Uber added airport-specific models with terminal-level destination points and
incorporated walking time estimates from the terminal exit to the curb. They also added
a "passenger in airport" signal (detected from the passenger's last known indoor location
before they went below GPS detection in the terminal) to trigger the airport-specific
model.

**Lesson:** ETA models are brittle at edge cases (airports, stadiums, venues with complex
access roads). Systematic evaluation at specific venue types, not just overall accuracy,
is necessary.

### 7.5 Accuracy Metrics

| Metric | Definition | Typical Target |
|--------|------------|----------------|
| MAE | Mean Absolute Error in seconds | < 60 seconds |
| MAPE | Mean Absolute Percentage Error | < 10% |
| p50 accuracy | % of ETAs within ±2 min | > 70% |
| p90 accuracy | % of ETAs within ±5 min | > 90% |
| Late arrivals | % where actual > ETA | < 40% |

Note: "late" is generally worse for user experience than "early" — if you tell someone
"8 minutes" and the car arrives in 6, they are fine. If you say "8 minutes" and the car
arrives in 15, they are frustrated. This asymmetry drives some systems to report a
slightly optimistic p40 rather than the p50 median.

### 7.6 Intern → Staff: ETA

**Intern:** "Distance divided by speed limit."
(Missing traffic entirely.)

**Junior (L3):** "Use real-time traffic data to adjust speed estimates."
(Right idea, no data pipeline design.)

**Mid-Level (L4):** "Historical speed by time-of-day + real-time GPS probe aggregation.
Combine in a model. Store historical in a lookup table by (segment, day, hour)."

**Senior (L5):** "Feature engineering matters: weather coefficient, special events,
historical variance (high variance segments need wider confidence intervals). Model
output should be p50 and p90, not just a point estimate. Retrain weekly on new probe data."

**Staff (L6):** "ETA accuracy degrades significantly at specific venue types and at
prediction horizons beyond 30 minutes. The right architecture: a base model (gradient
boosted trees) for the common case, plus venue-specific fine-tuned models for airports,
stadiums, hospitals. The probe data pipeline needs low latency — Kafka ingestion, Flink
streaming aggregation to 5-minute rolling averages per segment, stored in Redis for
real-time lookup. Historical model trained on a 90-day window (longer = stale; shorter
= underfits seasonal patterns). Key operational metric: ETA bias by venue type,
hour-of-day, and weather condition — monitoring only overall MAE misses systematic errors."

### 7.7 Brainstorming Q&A

**Q: How do you handle ETA for a route that passes through an area with no probe data
(e.g., a remote road)?**

When a road segment has few or no recent probe measurements, you fall back to historical
data. If historical data is also sparse (a rarely-used road), you fall back to the road
type default: highway = 90% of speed limit, arterial = 70% of speed limit, residential
= 50% of speed limit. These defaults are calibrated from global averages across all
similar road types where data exists. The model should also widen its confidence interval
for low-probe-density segments — if we have 2 probes saying the road is clear, our
uncertainty is much higher than if we have 200 probes. Some production systems include
a "probe density" feature explicitly in the model so it can learn to produce wider
intervals when data is sparse.

**Q: How does real-time traffic affect Contraction Hierarchies? Does the preprocessing
need to be redone every time traffic changes?**

This is an important interaction. The base CH graph is precomputed with "expected" travel
times (average historical weights). Real-time traffic changes the effective edge weights,
but redoing the full CH preprocessing for every traffic update is impossible — preprocessing
takes hours or days. The solution: "overlay" the traffic data at query time. The CH query
fetches the current travel time multiplier for each segment from a fast lookup table
(populated by the real-time Flink traffic pipeline), and uses the modified weight during
the bidirectional Dijkstra traversal. The CH's contracted shortcut graph still exists,
but for segments where real-time traffic is significantly different from the precomputed
base, the shortcut weights are recalculated dynamically. This is an approximation — some
shortcuts that pass through congested areas will still be taken even though their actual
weight has increased. Production systems handle this by running a local Dijkstra search
around heavily congested areas rather than relying on precomputed shortcuts through them.

---

## Part 8: Map Tiles and Rendering

### 8.1 The Tile System

A map is not served as one giant image. It is divided into tiles — small square image
pieces typically 256×256 pixels. The tile system is organized into zoom levels:

- **Zoom 0:** The entire Earth fits in one tile (very low detail — just continents)
- **Zoom 8:** City-level detail (San Francisco and surroundings on a screen)
- **Zoom 14:** Street-level detail (individual blocks visible)
- **Zoom 18:** Building-level detail (individual houses)
- **Zoom 22:** Maximum zoom (sub-meter resolution, used for indoor maps)

At each zoom level, the Earth is divided into 4^z tiles (4 tiles at zoom 1, 16 at zoom 2,
etc.). At zoom 18, there are 68 billion tiles. The URL format is:
`/tiles/{z}/{x}/{y}.png` where z = zoom level, x/y = tile coordinates.

```
TILE PYRAMID:

Zoom 0 (1 tile):
+--------+
| World  |
+--------+

Zoom 1 (4 tiles):
+----+----+
| NW | NE |
+----+----+
| SW | SE |
+----+----+

Zoom 2 (16 tiles): ... 4x4 grid
Zoom 3 (64 tiles): ... 8x8 grid
...

Total tiles across all zoom levels 0-22: ~1.4 trillion tiles
Storage for raster tiles (compressed PNG): ~50 TB for the whole planet
(in practice, most tiles are ocean/wilderness and generated on demand or skipped)
```

### 8.2 Raster Tiles vs. Vector Tiles

**Raster Tiles (Traditional Google Maps)**

Raster tiles are pre-rendered PNG or JPEG images. The tile server renders map segments
into images offline (during the map build process) and stores them. Serving is trivial —
just return the image file for the requested (z, x, y). Clients display the image
without needing to understand map data.

Downsides: Large storage, fixed rendering style (cannot change colors client-side),
labels are baked into the image (cannot be resized or translated dynamically), blurry
when zoomed between levels.

**Vector Tiles (Modern Google Maps, Mapbox)**

Vector tiles contain the raw geographic data (road centerlines, building polygons, labels)
in a compact binary format (Protocol Buffers). The client-side rendering engine draws
the map from this data at runtime. 

Advantages: Much smaller file sizes (10–50× smaller than PNG), client can rotate/tilt
the map smoothly, labels can be dynamically sized for the screen resolution, rendering
style can be changed without refetching tiles (day/night mode switch is instant).

Downsides: Requires a rendering engine on the client (significant code, CPU, and GPU
usage on the device). Not suitable for static images or headless server-side rendering.

**Google Maps switched from raster to vector tiles** for the mobile app around 2013.
Apple Maps and Mapbox also use vector tiles. For an interview, mentioning this transition
and its tradeoffs demonstrates up-to-date knowledge.

### 8.3 Tile Serving Architecture

```
TILE SERVING ARCHITECTURE:

User's Browser/App
       │
       │  GET /tiles/14/2620/6331.pbf
       ↓
[CDN Edge Node (Cloudflare / Akamai)]
  Cache hit rate: > 99% for popular zoom levels
       │
       │  Cache miss (< 1%)
       ↓
[Tile Server Fleet]
  Checks tile cache (Memcached / Redis)
       │
       │  Cache miss
       ↓
[Tile Generator]
  Renders tile from vector database
  (PostGIS with OSM data)
  Stores rendered tile in cache
```

The CDN cache hit rate is critical. Most users view maps of cities at medium zoom levels —
the same tiles get requested millions of times per day. Cache hit rate for popular tiles
exceeds 99.9%. Only very-high-zoom tiles of remote areas miss the cache regularly.

### 8.4 The Map Update Pipeline

When OSM data changes (a new road opens, a building is demolished), the change needs to
propagate to the tile cache. The pipeline:

1. **OSM change detection:** Subscribe to OSM's planet diff feed (published every minute)
2. **Data ingestion:** Parse OSM diff, update the PostGIS vector database
3. **Affected tile invalidation:** Compute which tiles intersect the changed geometry
4. **Tile regeneration:** Re-render affected tiles, update the CDN cache
5. **Time to live on CDN:** Tiles have TTLs — most are cached for 24–72 hours

For Google Maps' proprietary data, the update pipeline is more complex: manual edits,
satellite imagery analysis, Street View data, user-submitted corrections, and local
guide contributions all feed into the same pipeline.

### 8.5 Brainstorming Q&A

**Q: How do you handle map label placement — making sure street names don't overlap?**

Label placement is a classic computational geometry problem. Each label (road name,
POI label, city name) has a position (along a road centerline, or at a point), a size
(depends on font size and label length), and a priority (highway names have higher
priority than residential street names). The constraint: no two labels should overlap.

The solution is a greedy label placement algorithm: sort labels by priority, then place
each label in the first available position that does not conflict with already-placed
labels. Vector tile rendering engines run this algorithm on the client side at render
time. The advantage of client-side label placement is that it adapts to the exact screen
size, rotation, and zoom level — labels placed correctly for every device without
server-side knowledge of the screen dimensions. This is one of the key advantages of
vector tiles over raster tiles: raster tiles bake in the label positions at render time,
leading to overlap issues when a user rotates the map or zooms to a fractional level.

**Q: How are map tiles pre-generated at scale? Rendering 68 billion tiles sounds expensive.**

The key insight is that most tiles never need to be pre-generated. At very high zoom
levels (18–22), the vast majority of the Earth's surface is empty — ocean, wilderness,
agricultural land with no features. These tiles can be generated on demand (lazy
rendering) when first requested, then cached. Only the most-requested tiles (cities at
popular zoom levels) need to be pre-generated.

In practice, Google and Mapbox use a tiered strategy: zoom levels 0–12 are pre-rendered
for the entire planet (a manageable number of tiles). Zoom levels 13–16 are pre-rendered
for populated areas. Zoom 17+ is rendered on demand. The rendering infrastructure uses
massive parallelism — thousands of rendering workers running simultaneously, each
handling a batch of tiles. The initial planet-wide render takes weeks but subsequent
incremental updates are much faster (only re-render tiles intersecting changed geometry).

---

## Part 9: Live Traffic — GPS Probes to Color-Coded Roads

### 9.1 GPS Phones as Traffic Sensors

Every phone running Google Maps or Waze while navigating is sending its current location
and speed back to Google's servers. These "probe vehicles" are massively distributed
traffic sensors. Waze, which crowdsourced traffic data explicitly, was acquired by Google
in 2013 partly for this probe network.

At scale: Google Maps has roughly 1 billion monthly active users. Even if 1% are actively
navigating at any given moment, that is 10 million probe vehicles updating their speed
every few seconds. This gives unprecedented coverage of road conditions in real time.

### 9.2 The Traffic Pipeline

```
ASCII DIAGRAM: LIVE TRAFFIC PIPELINE

GPS Probes (phones navigating):
       │
       │  (lat, lng, speed, heading, timestamp) every 5-10 seconds
       ↓
[Ingestion Layer]
  Kafka cluster — billions of events/day
  Topic: probe-data, partitioned by geographic region
       │
       ↓
[Stream Processing — Apache Flink]
  1. Map each probe to a road segment (map matching)
  2. Aggregate speed measurements per segment (5-min sliding window)
  3. Compare to historical baseline
  4. Classify: FREE_FLOW, SLOW, HEAVY, STANDSTILL
  5. Emit traffic events to traffic-state topic
       │
       ↓
[Traffic State Store]
  Redis: (segment_id → current_speed, traffic_class)
  Updated every 1-5 minutes per segment
       │
       ├─── [Routing Service]  (uses traffic state for ETA calculation)
       │
       ├─── [Map Tile Service]  (uses traffic state for color overlay)
       │
       └─── [Incident Detection Service]
            Anomaly detection: unusual slowdown → potential incident
            Triggers validation (user reports, camera feeds)
            If confirmed: adds incident marker to map
```

### 9.3 Map Matching — Probe to Road Segment

A GPS probe has raw coordinates (37.7749° N, 122.4194° W). To aggregate traffic data,
you need to know which road segment the probe is on. This is the "map matching" problem.

**Naive approach:** Find the nearest road segment (by Euclidean distance from the probe
to road centerline segments). Works most of the time but fails at intersections (where
two roads cross) and parallel roads (a probe on a freeway might snap to an adjacent
parallel service road).

**HMM-based map matching:** Treat the sequence of GPS probes as observations and the
road segments as hidden states. A Hidden Markov Model (HMM) finds the most likely
sequence of road segments given the observations, taking into account road topology
(you cannot jump from one road to another without using an intersection). This is the
state-of-the-art approach and handles noisy GPS well.

### 9.4 Incident Detection

When traffic suddenly slows to a crawl on a normally fast segment, it could mean:
an accident, a disabled vehicle, road work, a police checkpoint, or a sudden weather
event. The traffic pipeline runs anomaly detection to flag these events.

**Statistical anomaly detection:** For each segment, maintain the historical speed
distribution by time-of-day. If the current speed is more than 2–3 standard deviations
below the historical mean for this time, flag it as a potential incident.

**Validation:** Flagged segments trigger validation through multiple channels:
- Other probe vehicles in the area — are they also slow?
- User reports (the "Report incident" button in Waze/Maps)
- Fixed traffic cameras (where available)
- Local news feeds (for major incidents)

Only after validation is an incident shown on the map. False positives (flagging normal
congestion as an incident) degrade user trust.

### 9.5 The Lyft Driver Location Staleness Incident

In 2017, Lyft experienced a production incident where driver locations shown to passengers
were up to 90 seconds stale. The root cause: a Redis cluster failover occurred during
peak hours, and the location service's Kafka consumer group lost its offset position
and began re-reading messages from a 90-second-old offset. New location updates from
drivers were not being applied to Redis; instead, old updates were being reprocessed
and overwriting the correct current locations.

The incident caused passengers to see driver icons frozen in place or moving erratically.
In one case, a passenger was shown their driver approaching from the wrong direction and
walked to the wrong side of the street to wait.

**Root cause:** Kafka consumer offset management bug — when the consumer group rebalanced
after the Redis failover, it reset to the last committed offset rather than the latest
offset. The committed offset was 90 seconds behind because the offset was committed every
30 seconds and multiple failures had stacked.

**Fix:** 1) Change offset commit strategy to commit on every successful Redis write
(instead of on a timer). 2) Add a staleness metric: monitor the difference between
Kafka message timestamp and current time. Alert if lag exceeds 15 seconds.
3) Add a "location freshness" field to the API response so the passenger app can show
"driver location last updated N seconds ago" when staleness exceeds a threshold.

**Lesson:** Location systems need explicit staleness tracking. A user-visible "last updated"
timestamp both informs users and creates operational pressure to fix staleness issues quickly.

### 9.6 Brainstorming Q&A

**Q: How does Waze know about a police speed trap on a specific road?**

Waze relies on user-submitted reports. When a user taps "Report" → "Police" in the Waze
app, their current location and the reported incident type are sent to Waze's servers.
The incident is immediately shown to other nearby users. The system has a confidence
model: a single report creates a low-confidence incident marker. If multiple users in
the same area independently report the same incident type within a short time window,
the confidence increases and the marker becomes more prominent. Reports are automatically
removed after a timeout (police traps last 1–2 hours before auto-removal) or when a
user reports the incident as "no longer there." Waze also uses the "thumbs up" interaction:
nearby users can confirm an existing report, which increases its confidence and extends
its lifetime. The whole system is a distributed consensus mechanism — individual reports
are noisy, but aggregate reports are reliable.

**Q: How does the traffic data pipeline handle peak load — say, New Year's Eve when
everyone is navigating simultaneously?**

New Year's Eve is the single biggest traffic event for navigation systems — tens of
millions of people navigating at midnight in time zones around the world, combined with
unusual traffic patterns (parties, fireworks, everyone going home at the same time).
Probe data volume can spike to 5–10× normal. The Kafka ingestion layer handles this
with auto-scaling — Kafka clusters are provisioned for peak plus a safety margin, and
Kafka's partitioned design means you can add consumer instances horizontally without
downtime. The Flink processing layer also auto-scales: new processing instances are
added when Kafka lag grows. The bigger challenge is the map tile serving layer —
New Year's Eve causes millions of simultaneous map refreshes. CDN edge caches absorb
most of this, but origin servers may see a traffic spike for tiles that expire around
midnight. Pre-warming CDN caches with freshly-rendered traffic overlay tiles before
the event is a standard operational practice.

---

## Part 10: The 45-Minute Interview Framework

### 10.1 Structuring the Interview

Design questions about Uber or Google Maps are dangerous because they contain 4–6
distinct sub-problems. Candidates who try to cover everything at equal depth run out of
time and produce a shallow, unfocused design. The right approach: deliberate scoping,
deep execution on the selected scope.

**First 5 Minutes: Clarify and Scope**

Ask the interviewer which system to focus on. Suggest a scope: "For 45 minutes, I'd
like to focus on the driver location tracking system and proximity search, as these are
the highest-throughput components and have the most interesting design decisions. I'll
sketch the routing and ETA systems at the end but won't go deep. Sound good?"

This move does several things: demonstrates awareness of scope (L5+ behavior), gives
you agency over what to design deeply (play to your strengths), and sets clear
expectations with the interviewer.

**Next 10 Minutes: Requirements and Numbers**

Functional requirements:
- Drivers update their location every 4 seconds
- Passengers can find nearby available drivers within 2km
- Passengers on active trips see their driver's real-time location
- (Optional: routing, ETA)

Non-functional requirements:
- Location update write throughput: 1.25M/sec (5M drivers ÷ 4 seconds)
- Proximity search latency: < 100ms p99
- Trip tracking latency (driver update to passenger UI): < 5 seconds
- Availability: 99.99% (location service is core to Uber's business)

Numbers to cite:
- 5M active drivers globally
- 1.25M location writes/second
- 500K concurrent rides
- Geohash-6 for 2km proximity (1.2km × 0.6km cells)
- Redis GEOSEARCH < 1ms

**Next 25 Minutes: Deep Design**

Walk through: driver app → ingestion (WebSocket/gRPC) → Kafka buffer → location service
consumers → Redis GeoSets + Cassandra. Then: proximity search query path, geohash
encoding, 9-cell search, Haversine filter. Then: trip tracking pub/sub. Call out the
sharding strategy explicitly.

**Final 5 Minutes: Sketch Routing and ETA**

Brief sketch: road graph, Contraction Hierarchies, ETA as historical + real-time ML.
One minute each. Do not try to go deep.

### 10.2 L5 vs. L6 Calibration

The difference between an L5 and L6 response in a location systems interview:

| Dimension | L5 Response | L6 Response |
|-----------|-------------|-------------|
| Spatial indexing | Correctly chooses geohash, explains boundary fix | Reasons about precision choice (geohash-6 vs. 7), S2 for polygon zones |
| Redis sharding | "Shard by city" | "Shard by geohash-2 prefix, explain the cross-shard edge case for drivers near region boundaries" |
| Kafka role | "For durability" | "For backpressure, offset management, explains consumer group rebalancing risk and mitigation" |
| ETA | "ML model with traffic data" | "Feature engineering: probe density as model input, output as distribution, venue-specific models, bias metrics" |
| Incidents | Doesn't mention | "Redis TTL for offline detection, Kafka lag as staleness alert, circuit breaker on location service" |
| Trade-offs | Lists pros/cons of each option | Makes a specific recommendation with quantified reasoning ("geohash-6 gives 9 cells for 2km radius; geohash-5 would require only 1 cell but with 50× more drivers per cell, making the Haversine filter step O(N) expensive") |

### 10.3 Key Numbers for the Interview

```
NUMBER CHEAT SHEET:

SCALE:
- 5M active drivers (Uber global peak)
- 1.25M location writes/second
- 500K concurrent trips
- 10M proximity searches/day

LATENCY:
- Driver update to Redis: < 50ms
- Proximity search (Redis GEOSEARCH): < 1ms
- End-to-end "find nearby drivers": < 100ms
- CH routing query: < 1ms
- End-to-end route computation: < 200ms

SPATIAL:
- Geohash-6: 1.2km × 0.6km cell
- Geohash-7: 153m × 153m cell
- S2 level 12: ~2km² cell
- OSM: 100M nodes, 1B edges

STORAGE:
- Redis per-driver entry: ~100 bytes (GeoSet member)
- 5M drivers × 100B = 500MB in Redis (fits on one machine!)
- Cassandra history: ~100B/record × 1.25M/sec × 30 days = 324TB

ROUTING:
- CH preprocessing: 1-3 days on planet graph
- CH query: < 1ms (vs. Dijkstra: 27 seconds)
```

### 10.4 Brainstorming Q&A

**Q: What if the interviewer asks you to design both Uber AND Google Maps in the same
session?**

This is intentional pressure-testing. The interviewer wants to see how you handle scope.
The correct response: "These are actually four different systems — driver location
tracking, proximity search, map routing, and ETA. I can sketch all four at high level,
or go deep on any two. What would be most valuable to you?" If the interviewer says "go
deep on all," push back gently: "In 45 minutes, I can give you a solid deep design on
two, or a shallower design on four. For a real system design review, I'd want more time.
Which two should we prioritize?" This shows judgment. A candidate who tries to do
everything in 45 minutes and produces shallow answers for all four looks worse than a
candidate who does two things well.

**Q: How do you handle the interviewer who keeps asking "what else?" — probing for
more depth on every component?**

This is the "depth vs. breadth" dynamic in real interviews. The right strategy: when
you finish describing a component, pre-empt the "what else?" by mentioning one trade-off
or failure mode you considered. For example, after explaining geohash sharding: "One
edge case I'd flag: drivers near regional shard boundaries need their location removed
from one shard and added to another — this is a two-operation sequence that is not
atomic in Redis. I'd handle this with at-least-once semantics: write to the new shard
first, then remove from the old shard. A brief window where the driver appears in both
shards is acceptable; appearing in neither is not."

Pre-surfacing edge cases shows depth without the interviewer having to extract it from
you. It also controls the interview pace — you spend time on the nuances you know well
rather than being pushed to areas you know less well.

**Q: What if you don't know Contraction Hierarchies? Can you still pass an L5 interview?**

Yes, with conditions. The interview is testing whether you know that naive Dijkstra
doesn't work at scale and that routing requires offline preprocessing. If you say
"We'd precompute the graph using a hierarchical routing algorithm — I'm familiar with
the concept of Contraction Hierarchies at a high level: contracting less important nodes
and precomputing shortcuts so query time is milliseconds, not seconds. I'd lean on
libraries like OSRM for the actual implementation" — that is an honest, correct answer
that passes an L5 bar. What fails is saying "We'd run Dijkstra" without any awareness
that this is infeasible at scale, or worse, saying "We'd use BFS" (BFS doesn't work
on weighted graphs at all).

---

## Part 11: Real Incidents and Operational Lessons

### 11.1 The Uber Surge Pricing Zone Bug (2015)

**What happened:** During a snowstorm in New York City in January 2015, Uber's surge
pricing system applied incorrect surge multipliers to a large portion of Manhattan.
Some areas showed 1.0× (normal) pricing while adjacent areas showed 7× or 8× surge.
The boundary between surge zones was misaligned with the actual driver density patterns.

**Root cause:** Uber's surge pricing zones were defined as polygons in a configuration
database. The system that checked whether a driver or passenger was "inside" a surge zone
used a point-in-polygon algorithm that had a bug in handling the polygon boundaries.
Points exactly on the polygon boundary (or very near it, due to floating-point precision)
were sometimes classified as inside and sometimes outside, depending on which direction
the polygon vertices were wound (clockwise vs. counterclockwise). During the snowstorm,
when many drivers were clustered near zone boundaries (waiting in sheltered areas), the
boundary classification errors caused drivers and passengers in the same physical block
to be assigned different surge multipliers.

**Fix:** Uber switched from exact polygon boundary checks to geohash-based zone
membership. Surge zones are now represented as sets of geohash cells. A driver's zone
membership is determined by their geohash prefix, not a floating-point polygon
intersection. This is more robust because the zone boundaries are always aligned to
the geohash grid — there is no ambiguity about which zone a cell belongs to.

**Lesson:** Floating-point geometry is dangerous for business logic. When precision
matters (pricing, legal jurisdiction, service area), use discrete cell-based
representations rather than continuous polygon math.

### 11.2 The Google Maps Wrong Turn Incident (2013, Kenya)

**What happened:** Google Maps routing sent drivers onto a road that was impassable
(a seasonal river crossing that was flooded during the rainy season). The OSM data
for the road did not have a "seasonally impassable" tag, and Google's routing algorithm
treated it as a normal passable road. Several drivers followed the navigation into
floodwaters.

**Root cause:** The routing graph had no representation of seasonal road conditions.
The road existed in the map; there was no mechanism to flag it as closed during flood
season. OSM contributors in the region had reported the condition, but the change had
not been incorporated into the routing graph before the incident.

**Fix:** Google added support for time-conditional edge weights and blocklists.
Roads can now be tagged as "closed during rainy season" with a date range. The routing
engine applies these blocklists before query time. Google also expanded local data
partnerships (with local transportation authorities) to get faster updates on road
conditions in remote regions.

**Lesson:** Map data quality is as important as routing algorithm correctness. A correct
algorithm on wrong data produces wrong answers. Systems that ingest community-sourced
map data (like OSM) need rigorous validation pipelines before changes affect the routing
graph.

### 11.3 The Redis GeoSet Memory Leak (Uber Internal, 2018)

**What happened:** Uber's location service experienced gradual Redis memory exhaustion
over a 2-week period. The Redis instances for the driver location GeoSets were consuming
2–3× more memory than expected based on the number of active drivers.

**Root cause:** The code that removed drivers from the GeoSet when they went offline
had a race condition. The sequence was: (1) driver sends final location update, (2)
driver app closes, (3) heartbeat monitor detects driver offline after 30-second timeout,
(4) system calls ZREM to remove driver from GeoSet. But in step (1), the location update
wrote to a new regional GeoSet after the driver had crossed a geographic shard boundary
earlier in the session. The ZREM in step (4) was removing the driver from the old regional
GeoSet (where the driver started the session) but not from the new one (where the driver
had moved to). Over 2 weeks, hundreds of thousands of ghost driver entries accumulated
in the "new region" GeoSets.

**Fix:** Track the driver's current shard assignment explicitly, stored in a separate
Redis hash (driver_id → current_shard). The ZREM operation looks up the current shard
first, then removes from the correct set. On startup after a crash, the heartbeat monitor
scans all shards for the driver's GeoSet entry and removes stale entries from all of them.

**Lesson:** Cross-shard operations are a common source of consistency bugs. Any operation
that touches multiple shards (driver moves between regions, driver goes offline) needs
careful coordination. Adding a single source of truth for "which shard owns driver X"
prevents split-brain states.

### 11.4 Operational Best Practices

**1. Explicit Staleness Tracking**

Every location service should expose the age of its data, not just the data itself.
The API response for "get nearby drivers" should include a response_freshness_ms field.
The Kafka consumer should emit a kafka_lag_seconds metric. Alert when lag > 15 seconds.
This surfaced the Lyft incident within minutes instead of discovery through user complaints.

**2. Health Endpoints per Shard**

Each Redis shard should have a health check endpoint that returns: current GeoSet member
count, memory usage, write throughput (operations/second), last write timestamp.
Sudden drops in member count (driver ghost eviction bug) or spikes in memory (memory
leak) are detected immediately rather than during a degraded incident.

**3. Chaos Engineering for Location Systems**

Deliberately kill a Redis shard during a load test and measure: how long until failover
completes, how many location updates are buffered in Kafka during the failover, what
is the staleness of driver locations during and immediately after recovery. Run this
quarterly. Location services at Uber and Lyft regularly run failover drills.

**4. Load Testing with Realistic Patterns**

Location update load is not uniform throughout the day — there are morning rush and
evening rush peaks, and event-based spikes (concerts, sports games). Load tests should
simulate the realistic diurnal pattern, not just a flat synthetic load. A system that
handles 1M writes/second for 10 minutes may fail at 800K writes/second sustained for
3 hours due to slow memory leaks or connection pool exhaustion.

---

## Common Interview Mistakes

### Mistake 1: Treating "Design Uber" as One Problem

The #1 failure mode: jumping straight to drawing boxes labeled "Location Service" and
"Routing Service" without separating the sub-problems. Interviewers at L5+ expect you
to immediately identify and scope the problem. Failure to do so signals shallow domain
knowledge.

**Fix:** Before drawing anything, say: "This question covers at least three distinct
systems — driver location tracking, proximity search, and routing. Let me separate
them and then we can decide which to go deep on."

### Mistake 2: Forgetting the Boundary Problem in Geohash

Very commonly, candidates correctly identify geohash as the spatial index but then
describe a proximity query as "prefix scan on the target geohash cell." The interviewer
will ask "what happens to drivers near the cell boundary?" Candidates who do not have
a ready answer lose points here.

**Fix:** Always say "prefix scan on the target cell and its 8 neighboring cells, then
filter by Haversine distance." This should be reflexive — the boundary problem fix is
not an edge case, it is part of the correct algorithm.

### Mistake 3: Proposing Dijkstra for Planet-Scale Routing

Saying "we'd run Dijkstra on the road network" is a near-instant signal that you do not
understand routing at scale. Dijkstra on 1 billion edges takes 27 seconds. Google Maps
answers in 200 milliseconds. The gap requires offline preprocessing.

**Fix:** Know that routing requires preprocessing (Contraction Hierarchies or similar).
Even if you do not know CH in detail, say "we need an offline preprocessing step to
precompute shortcuts so queries can run in milliseconds." That is enough for L5.

### Mistake 4: Ignoring Write Throughput

Candidates who propose Postgres or MySQL as the driver location store without any thought
about 1.25M writes/second are demonstrating that they did not internalize the scale
requirement. B-tree indexes cannot be updated at that rate without significant hardware
and careful partitioning.

**Fix:** Start with the write throughput number (1.25M/sec) and then justify your storage
choice. "At 1.25M writes/second, we need an in-memory store — Redis GeoSets with
horizontal sharding by geographic region."

### Mistake 5: Not Mentioning Kafka (or an Equivalent Buffer)

Connecting the driver app directly to Redis without an ingestion buffer is brittle —
any Redis slowdown causes backpressure to propagate all the way to the driver apps,
causing them to time out and retry. This amplifies load spikes.

**Fix:** Always include Kafka (or Kinesis, Pub/Sub, any durable queue) between the
driver app and the storage layer. Explain that Kafka absorbs traffic spikes and decouples
the ingestion rate from the Redis write rate.

### Mistake 6: Confusing Geohash Precision

Saying "we'd use geohash-3 for 2km radius" signals that you have not actually worked
with geohash. Geohash-3 cells are 156km × 156km — absurdly large for a 2km radius
search. Candidates who cite precision-to-cell-size mappings from memory (or who can
reason to the right answer: "precision 6 gives ~1km cells which is slightly smaller
than our 2km radius, so 9 cells give us about 3km × 3km coverage, which is correct")
demonstrate genuine knowledge.

**Fix:** Memorize the key precision levels:
- Precision 5: ~5km cells (too big, one cell covers too much)
- Precision 6: ~1km cells (right for 2km radius search)
- Precision 7: ~150m cells (right for 500m radius search)

---

## Exercises

**Exercise 1: Geohash Neighbor Calculation**

Implement a function `geohash_neighbors(geohash_str)` that returns the 8 neighboring
geohash cells. Test it with the San Francisco geohash "9q8yym" and verify that the
neighbors are geographically adjacent on a map. Then implement `proximity_search(lat,
lng, radius_km)` using geohash prefix scans on the 9 cells.

**Exercise 2: Redis GeoSet Benchmark**

Set up a Redis instance locally. Use GEOADD to insert 100,000 random (lat, lng) points
representing simulated drivers in New York City (lat 40.5–40.9, lng -74.0 to -73.8).
Run GEOSEARCH for a 2km radius from Times Square (40.7580° N, 73.9855° W) and measure
the latency. Now insert 1 million points and repeat. How does latency scale?

**Exercise 3: Quadtree Implementation**

Implement a basic quadtree in Python or Go that supports:
- `insert(lat, lng, driver_id)` — add a driver's position
- `query_radius(lat, lng, radius_km)` — return all drivers within radius
- `update(driver_id, lat, lng)` — move a driver to a new position

Test with 10,000 drivers and compare query latency to a brute-force O(N) scan.

**Exercise 4: Contraction Hierarchy Intuition**

Take a small road graph (20–30 nodes) representing a simple city grid. Manually apply
the contraction hierarchy algorithm: rank nodes by importance (number of shortcuts needed
to contract them), contract the least important nodes first, and add shortcut edges.
Then run a bidirectional Dijkstra search on the contracted graph. Count how many nodes
you explore vs. on the original graph.

**Exercise 5: ETA Feature Engineering**

Given a dataset of historical Uber trips (available on Kaggle: NYC Uber trips dataset),
build a simple ETA model. Features: pickup lat/lng, dropoff lat/lng, hour of day, day
of week, month. Target: actual trip duration. Use a gradient boosted tree (XGBoost or
LightGBM). Evaluate on a held-out test set using MAE and MAPE. Compare to the baseline
of trip distance ÷ average speed.

**Exercise 6: Traffic Anomaly Detection**

Given a stream of (segment_id, timestamp, speed) tuples, implement a streaming anomaly
detector that:
1. Maintains a rolling 7-day average speed by (segment_id, hour_of_day)
2. Flags any reading where current speed is more than 2 standard deviations below the
   7-day average for that hour
3. Requires 3 consecutive flagged readings before emitting an incident alert

Test with a simulated dataset where you inject a 30-minute slowdown on one segment.

**Exercise 7: Geohash vs. S2 Covering**

Pick a surge pricing zone shape — use the approximate outline of "Downtown San Francisco"
(the Financial District + SoMa roughly). Compute two coverings:
1. Geohash-6 cells that intersect this polygon
2. S2 level-12 cells that cover this polygon

Count the number of cells needed for each. Which requires fewer cells? Which has less
"overage" (area outside the polygon but inside the covering)?

**Exercise 8: Full System Load Calculation**

Validate the architecture's capacity for 1.25M location writes/second:
- If each Redis GEOADD takes 0.1ms of Redis CPU time, how many Redis instances do you
  need to absorb 1.25M writes/second?
- If Kafka is partitioned across 20 brokers, what is the per-broker write rate?
- If each location update is 200 bytes, what is the Kafka ingestion bandwidth in GB/sec?
- If the Cassandra location history is retained for 30 days, what is the total cluster
  size in TB (assuming 2× compression and 3× replication)?

---

## Homework

**Homework 1: Read the OSRM Architecture**

OSRM (Open Source Routing Machine) is an open-source CH-based router used by many
companies. Read the OSRM technical architecture documentation (available on GitHub at
Project-OSRM/osrm-backend). Focus on: how the preprocessing pipeline works, how the
CH graph is stored, and how queries are executed. Write a 1-page summary of the key
design decisions.

**Homework 2: Implement Geohash from Scratch**

Without using any geohash library, implement the geohash encoding algorithm in Python:
- Input: (latitude, longitude, precision)
- Output: geohash string
- Test against a known-good library (python-geohash or pygeohash)

The exercise forces you to understand the binary interleaving and base-32 encoding.

**Homework 3: Explore the H3 Library**

Uber's H3 is an alternative to geohash that uses a hexagonal grid instead of a
rectangular grid. Hexagonal cells have uniform distance from center to all 6 neighbors
(unlike rectangular cells where corner neighbors are farther than edge neighbors).
Install the h3-py Python library, encode some locations, and compare the cell boundary
properties to geohash. Write a short comparison: when would you prefer H3 over geohash?

**Homework 4: ETA Confidence Intervals**

Using the NYC taxi dataset (publicly available), train an ETA model and evaluate it on
a test set. Then implement a prediction interval: for each test example, compute the
p10, p50, and p90 predicted travel time (use quantile regression or prediction intervals
from a Random Forest). What fraction of actual trip times fall within your p10–p90
interval? This is called the "calibration" of your uncertainty estimate — well-calibrated
models have 80% of actuals within the p10–p90 interval.

**Homework 5: Design Review**

Find a public design doc or engineering blog post about a location-based system (Uber
Engineering Blog, Lyft Engineering Blog, DoorDash Engineering Blog, and Foursquare
Engineering have all published relevant posts). Read it critically: what design decisions
did they make? What trade-offs did they discuss? What would you have done differently
based on what you learned in this chapter? Write a 1-page critical analysis.

---

## Part 12: H3 — Uber's Hexagonal Spatial Index

### 12.1 Why Uber Replaced Geohash with Hexagons

Uber open-sourced H3 in 2018, their production spatial indexing library. It replaced
geohash for most internal use cases. The reason is a geometric property of rectangular
vs. hexagonal grids.

**The distance problem with rectangular cells**:
In a geohash grid, a cell has 8 neighbors. But the 4 edge neighbors are at distance
*d*, while the 4 corner neighbors are at distance *d√2 ≈ 1.41d*. This asymmetry
creates artifacts: a driver at the corner of a cell is "just as close" as one at
the edge, but their geohash distance is 41% farther in Euclidean space.

**Hexagonal cells have uniform neighbor distance**:
A hexagon has 6 neighbors. Every neighbor center is equidistant from the current cell
center. This means "ring 1" (immediate neighbors) is a true circle, not an octagon
with stretched corners. For proximity calculations, this gives more accurate results
without post-filtering.

```
RECTANGULAR GRID vs. HEXAGONAL GRID
=====================================

  Geohash (rectangular):          H3 (hexagonal):
  
  ┌───┬───┬───┐                  / \ / \ / \
  │ N │ N │ N │                 │ N │ N │ N │
  ├───┼───┼───┤                  \ / \ / \ /
  │ N │ X │ N │                   │ N │ X │ N │
  ├───┼───┼───┤                  / \ / \ / \
  │ N │ N │ N │                 │ N │ N │ N │
  └───┴───┴───┘                  \ / \ / \ /
  
  Corner neighbors:               All neighbors:
  distance = d√2                  distance = d (uniform!)
  
  Problem: geohash "ring-1"       Advantage: true circular coverage
  search is actually an octagon   with no corner artifacts
```

### 12.2 H3 Resolution Levels

H3 defines 16 resolution levels (0–15). The levels most relevant to Uber:

| H3 Level | Cell Edge Length | Cells Worldwide | Use Case |
|----------|-----------------|-----------------|----------|
| 7        | 1.2 km          | 98M             | Coarse proximity search |
| 9        | 174 m           | 8.1B            | Surge pricing zones |
| 11       | 25 m            | 580B            | Street-level driver tracking |
| 13       | 3.6 m           | 41T             | Parking spot precision |

For driver proximity search at Uber, resolution 9 (~174m cells) is typical: fine
enough for accurate matching, coarse enough for manageable index cardinality.

### 12.3 H3 vs. Geohash Trade-offs

| Property | Geohash | H3 |
|----------|---------|-----|
| Cell shape | Rectangle | Hexagon |
| Neighbor distance | Non-uniform (√2 for corners) | Uniform |
| Parent/child hierarchy | Yes (prefix = parent) | Yes (but not prefix-based) |
| Library availability | Ubiquitous (everywhere) | Good (open-source, many languages) |
| Redis native support | Yes (Redis GeoSets use geohash internally) | No (must encode hex ID as sorted set score) |
| Learning curve | Low | Moderate |
| Production users | Most companies | Uber, Grab, others |

**When to mention H3 in an interview**: If the interviewer is from Uber or Lyft, or
if they explicitly ask about hexagonal indexing or Uber's approach, mention H3.
For most "design Uber" questions, geohash is the simpler and equally correct answer.
H3 signals extra depth; geohash signals solid fundamentals.

---

## Part 13: Driver-Rider Matching — From Proximity to Assignment

### 13.1 Proximity Search ≠ Matching

Finding nearby drivers (Part 4) and choosing which driver to dispatch are two different
problems. Proximity search answers "who is within 2 km?" — it returns a list. Matching
answers "which of those drivers should I assign to this rider?" — it picks one.

The naive approach: just pick the closest driver. This is wrong for two reasons:
1. The closest driver might already be being considered for another rider.
2. Global optimality: it might be better to assign a slightly farther driver to Rider A
   so that the closest driver is available for the even-more-urgent Rider B.

### 13.2 Uber's Batch Matching Approach

Uber runs a matching cycle every 5 seconds. Within each cycle:

1. **Collect**: gather all unmatched riders and all available drivers in the region.
2. **Build cost matrix**: for each (driver, rider) pair, compute a cost — primarily
   ETA from driver's current location to rider's pickup point (in seconds).
3. **Solve assignment**: find the assignment of drivers to riders that minimizes total
   cost. This is the classic **Assignment Problem** (bipartite matching).
4. **Dispatch**: send match notification to driver app and rider app simultaneously.

```
BATCH MATCHING CYCLE (every 5 seconds)
=========================================

  Unmatched riders: [R1, R2, R3]
  Available drivers: [D1, D2, D3, D4]
  
  Cost matrix (ETA in seconds):
  
           D1   D2   D3   D4
  R1:      30   90   45   120
  R2:      60   40   80   35
  R3:      20   55   15   70
  
  Optimal assignment (minimize total ETA):
  R1 → D3 (45s), R2 → D4 (35s), R3 → D1 (20s)
  Total cost: 100s
  
  Naive "closest first":
  R3 → D3 (15s), R1 → D1 (30s), R2 → D2 (40s)
  Total cost: 85s  ← cheaper! But only if all three happen simultaneously
  
  The difference: batch matching considers all assignments globally;
  "closest first" greedily picks best local choice at the moment it runs.
```

### 13.3 The Hungarian Algorithm vs. Heuristics at Scale

The classic solution to the assignment problem is the **Hungarian algorithm** —
O(n³) time where n is the number of riders (or drivers, whichever is larger). For
small n, this is fine. For Uber's peak load in a dense city (1,000+ riders + 5,000+
drivers in one region), O(n³) is too slow for a 5-second cycle.

Production approximations:
1. **Geographically limit candidates**: only consider drivers within X km — reduces n
   from thousands to dozens.
2. **Greedy with shuffle**: process riders in random order, assign each the best
   available driver. Fast but suboptimal.
3. **Auction algorithms**: each rider "bids" on drivers; drivers pick the highest
   bidder. Converges to near-optimal in O(n log n) iterations.

Uber has published that they use a combination of geographic pre-filtering (H3 cells)
and a greedy/auction hybrid for production matching, falling back to exact Hungarian
for small subproblems where it fits in budget.

### 13.4 When to Mention Matching in an Interview

For an L5 answer: "After finding nearby drivers via geohash/GeoSets, I'd assign the
closest available driver."

For an L6 answer: "Finding nearby drivers gives me a candidate set. The actual
assignment is an optimization problem — minimize total ETA across all unmatched
pairs in the region. Uber runs a batch matching cycle every 5 seconds using
geographically-filtered assignment. For small regions, the Hungarian algorithm works
directly; for dense cities, they use approximations like greedy assignment with
geographic pre-filtering."

---

## Part 14: Interview One-Liners

### 14.1 The Sentences That Signal Mastery

**Defining the core trade-off in one breath:**
> "Geo systems split into four sub-problems — driver tracking (write-heavy stream),
> proximity search (real-time spatial index), routing (offline-preprocessed graph),
> and ETA (ML on historical + probe data). Each has a different dominant technology."

**Explaining geohash boundary correction:**
> "Geohash proximity search must check the target cell AND its 8 neighbors, then
> post-filter with Haversine distance. Without the 8-neighbor check, drivers near
> a cell boundary are missed. Without the Haversine filter, you return false positives
> from the corner cells."

**Explaining why Dijkstra fails for planet-scale routing:**
> "Dijkstra on 100M nodes explores ~50M nodes for a long-distance query — that takes
> 27 seconds. Contraction Hierarchies preprocess the graph offline (1–3 days),
> reducing a long query to exploring ~thousands of nodes with bidirectional search — < 1ms."

**Explaining the 1.25M writes/second bottleneck:**
> "5 million active drivers sending one GPS update every 4 seconds = 1.25M writes/sec.
> This rules out a single Postgres instance and most off-the-shelf databases. Redis
> GeoSets sharded by geographic region handle this because each GEOADD is O(log N)
> at sub-millisecond latency, and geographic sharding means each shard handles only
> the drivers in its region."

**On Redis GeoSets vs. geohash strings:**
> "Redis GeoSets use geohash internally as the score in a sorted set, so GEOADD is just
> ZADD with a geohash-derived score. GEOSEARCH does a sorted-set range scan over the
> geohash space, then applies Haversine to filter. It's geohash at O(log N) with
> server-side filtering — the client never sees geohash strings."

### 14.2 The Decision Tree: Geo Questions in the Interview

```
  IS THE CORE PROBLEM FINDING NEARBY THINGS?
  ─────────────────────────────────────────────────────
  Yes → Geohash (simpler) or H3 (hexagonal, Uber-style)
        with Redis GeoSets. Always check 9 cells.
  
  IS THE CORE PROBLEM ROUTING ON A ROAD NETWORK?
  ─────────────────────────────────────────────────────
  Yes → Contraction Hierarchies (not Dijkstra, not A*).
        Offline preprocessing. Live traffic = edge weight overlay.
  
  IS THE WRITE THROUGHPUT > 100K/SECOND?
  ─────────────────────────────────────────────────────
  Yes → Kafka ingestion buffer + Redis GeoSets.
        Never write directly to Postgres for real-time location.
  
  DO YOU NEED TO SERVE MAP TILES?
  ─────────────────────────────────────────────────────
  Yes → Vector tiles (not raster). CDN-first.
        99%+ cache hit rate. Origin only for tile updates.
  
  DO YOU NEED TO MATCH DRIVERS TO RIDERS (NOT JUST FIND)?
  ─────────────────────────────────────────────────────
  Yes → Batch matching every 5 seconds. Assignment problem.
        Geographic pre-filter → greedy/Hungarian for the subproblem.
```

---

## KEY TAKEAWAYS

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    KEY TAKEAWAYS: LOCATION & MAPPING                         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  1. SEPARATE THE FOUR SUB-PROBLEMS                                            ║
║     Driver tracking ≠ proximity search ≠ routing ≠ ETA.                      ║
║     Each has different scale requirements and different solutions.            ║
║                                                                               ║
║  2. THE CORE SCALE NUMBER: 1.25M WRITES/SECOND                               ║
║     5M drivers × 1 update/4 sec. Everything flows from this:                 ║
║     → Redis GeoSets (not Postgres)                                            ║
║     → Kafka ingestion buffer (not direct writes)                              ║
║     → Geographic sharding (not random hashing)                               ║
║                                                                               ║
║  3. GEOHASH: ALWAYS CHECK 9 CELLS                                             ║
║     Target cell + 8 neighbors. Then Haversine filter.                        ║
║     Precision 6 = ~1km cells = right for 2km radius search.                  ║
║     Forgetting the boundary fix is the most common geohash mistake.           ║
║                                                                               ║
║  4. ROUTING REQUIRES PREPROCESSING                                            ║
║     Dijkstra: 27 seconds on planet graph. CH query: < 1ms.                  ║
║     The gap is offline preprocessing (Contraction Hierarchies).              ║
║     Preprocessing: 1-3 days. Queries: < 1ms. Stale graph: live overlay.      ║
║                                                                               ║
║  5. ETA IS NOT DISTANCE ÷ SPEED LIMIT                                        ║
║     Historical travel time by (segment, hour, day_of_week) +                 ║
║     real-time GPS probe data + ML model = production ETA.                    ║
║     Output should be a distribution (p50, p90), not a point estimate.        ║
║                                                                               ║
║  6. REDIS GEOSETS ARE THE RIGHT TOOL                                         ║
║     GEOADD: stores location as internal geohash in a sorted set.             ║
║     GEOSEARCH: radius query with Haversine filtering. < 1ms latency.         ║
║     Shard by geographic region. 5M drivers × 100B = 500MB (fits easily).    ║
║                                                                               ║
║  7. MAP TILES: CDN-FIRST, 99%+ CACHE HIT RATE                               ║
║     Raster tiles = pre-rendered PNGs (simple but large).                     ║
║     Vector tiles = geographic data rendered client-side (smaller, flexible). ║
║     Tiles are mostly static → CDN absorbs 99%+ of traffic.                  ║
║                                                                               ║
║  8. LIVE TRAFFIC = GPS PROBES + STREAM PROCESSING                            ║
║     Kafka ingest → Flink stream processing → Redis traffic state.            ║
║     Map matching: probe (lat,lng) → road segment (HMM approach).            ║
║     Anomaly detection: speed < (historical_avg - 2σ) → potential incident.  ║
║                                                                               ║
║  9. OPERATIONAL LESSONS FROM INCIDENTS                                        ║
║     Uber surge zone bug: use discrete cells, not floating-point polygons.    ║
║     Lyft staleness bug: track Kafka lag, expose data freshness in API.       ║
║     Redis memory leak: shard ownership must be explicitly tracked.           ║
║                                                                               ║
║  10. INTERVIEW FRAMEWORK                                                      ║
║     5 min: scope to 2 sub-problems. 10 min: requirements + numbers.         ║
║     25 min: deep design on scoped sub-problems. 5 min: sketch the rest.     ║
║     L6 signal: quantified trade-offs, edge cases, operational awareness.     ║
║                                                                               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  ONE-SENTENCE SUMMARY:                                                        ║
║  "Geo systems = Redis GeoSets (geohash, 9-cell search) for driver tracking   ║
║   + Kafka ingestion buffer for 1.25M writes/sec + Contraction Hierarchies    ║
║   for sub-ms routing + ML ETA on historical + probe data — four separate      ║
║   systems; the interview tests whether you can separate, size, and compose   ║
║   them under time pressure."                                                  ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

*Chapter 87 pairs with: Ch46 (Data Warehouse / OLAP) for ETA training data pipelines,
Ch83 (Chubby) for distributed coordination in the location service, Ch86 (Video
Streaming) for CDN architecture as applied to map tile serving.*

*Next chapter: Chapter 88 — Search Typeahead / Autocomplete (Trie vs. Inverted Index,
real-time prefix search at Google/Twitter scale)*
