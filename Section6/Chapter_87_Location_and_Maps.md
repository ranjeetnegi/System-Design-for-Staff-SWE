# Chapter 90: Location & Mapping — Uber / Google Maps / DoorDash

> "Design Uber" or "Design Google Maps" is the canonical geo-systems interview question.
> It tests spatial indexing, real-time location tracking, routing algorithms, and
> ETA estimation — four distinct systems that must compose cleanly under time pressure.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Geo-systems questions appear at Uber, Lyft, DoorDash, Google, Meta (location features),
and any company with a physical component. The unique challenge: location data is
continuous (not discrete like user IDs), requires spatial indexing (not standard B-trees),
and has real-time update requirements (driver location every second).

---

## Planned Content

### Part 1: The Problem Space — What Makes Geo Hard
- Latitude/longitude: 2D continuous space, not directly indexable
- Proximity queries: "find all drivers within 5km of this passenger" — SQL can't do this efficiently
- Real-time updates: 1 million drivers updating location every second = 1M writes/second
- Routing: shortest path on a graph with 100M+ nodes (road network)
- ETA: not just shortest path — traffic, time-of-day, historical speed data
- The four sub-systems: location storage, proximity search, routing, ETA

### Part 2: Spatial Indexing — Geohash, Quadtrees, and S2
- Why standard indexes fail for 2D range queries
- Geohash: encode lat/lng into a string prefix (nearby points share prefix)
  - "9q8yy" → 1km² cell; "9q8" → 78km² cell
  - Limitation: boundary problem (two points in adjacent cells may not share prefix)
- Quadtree: recursive subdivision of 2D space into 4 quadrants
  - Adaptive density: dense urban areas subdivide deeper
  - Used by: early Uber, many games
- S2 geometry (Google): Hilbert curve maps 2D space to 1D, preserving locality
  - S2 cells: 30 levels, from Earth-sized to 1cm²
  - Used by: Google Maps, Pokemon Go, Foursquare
- ASCII diagram: Geohash grid vs. Quadtree vs. S2 cell hierarchy

### Part 3: Driver Location Service (Real-Time Updates)
- Write path: driver app → location update service → location store
- 1M drivers × 1 update/second = 1M writes/second
- Storage options: Redis (in-memory, fast) + periodic flush to Cassandra/Bigtable
- Sharding: shard by geohash prefix (all drivers in a region on same shard)
- Pub/Sub fan-out: when a passenger requests a ride, subscribe to nearby driver location updates
- Heartbeat: drivers who stop sending updates are marked offline after N seconds
- ASCII diagram: driver location update pipeline

### Part 4: Proximity Search (Finding Nearby Drivers)
- Query: "find all drivers within radius R of point P"
- Approach 1: geohash range query — find all drivers in the same geohash cell(s)
  - Must expand to neighboring cells to handle boundaries
  - 8 neighbors for any geohash cell
- Approach 2: quadtree lookup — walk quadtree to find leaf nodes within radius
- Approach 3: S2 cell covering — compute the minimal set of S2 cells that cover the search area
- Ranking: sort by actual Haversine distance, then ETA
- Load and surge: how many drivers visible in surge pricing zones?

### Part 5: Road Network and Routing
- Data: OpenStreetMap (OSM) graph — 100M nodes, 1B edges for the full planet
- Algorithm: Dijkstra / A* for exact shortest path (too slow at global scale)
- Hierarchical routing: Contraction Hierarchies (CH) — precompute shortcut edges
  - CH preprocessing: 1 week on full planet; query: < 1ms
  - Used by: OSRM, Google Maps routing engine
- Turn restrictions, one-way streets, time-dependent edge weights (rush hour)
- ASCII diagram: road graph with contraction hierarchy shortcuts

### Part 6: ETA Estimation
- Naïve: shortest path distance / speed limit = wrong (ignores traffic)
- Historical speed: for each road segment, average speed by time-of-day + day-of-week
- Real-time traffic: aggregate current driver speeds on each segment (probe data)
- ML model: combine historical + real-time + weather + events → predicted travel time
- Uncertainty: ETA should be a distribution (p50 = 8 min, p90 = 12 min)
- Real incident: Uber 2019 — ETA model underestimated airport pickup times by 40%
  because it didn't account for terminal-to-curb walking time

### Part 7: Map Rendering and Tile Service
- Vector tiles vs. raster tiles
- Tile pyramid: zoom level 0 (whole world, 1 tile) → zoom level 20 (building-level, 1T tiles)
- Tile cache: heavily cached (static content changes rarely)
- Dynamic layers: traffic, construction, incidents (overlay on base tiles)
- Mobile optimization: predownload tiles for offline use

### Part 8: Interview Framework — Design Uber in 45 Minutes
- Scope clarification: ride matching, location tracking, routing, pricing? Pick 2.
- Standard scope for 45 min: location tracking + proximity search + ride matching
- Component walk-through: driver app → location service → matching service → rider app
- Scale numbers: 1M concurrent drivers, 500K concurrent rides, 10M location updates/minute
- Trade-offs to discuss: consistency of location data, geohash vs. S2, Redis vs. Cassandra
- L5 vs. L6 calibration: L5 draws boxes; L6 explains the quadtree depth decision based
  on driver density distribution in urban vs. rural areas

---

## Key Numbers to Memorize

| Metric | Value |
|--------|-------|
| Uber drivers (global) | ~5M active |
| Location update frequency | Every 4 seconds (Uber) |
| Proximity search radius | 5–10 km for ride matching |
| OSM road network | ~100M nodes, ~1B edges |
| Geohash precision 6 | ~1.2km × 0.6km cell |
| S2 level 12 | ~2km² cell |
| CH routing query latency | < 1ms |
| ETA accuracy target | ±2 minutes for p50 |

---

## The One-Sentence Summary

> "Geo systems = spatial index (geohash/quadtree/S2) for proximity search + real-time location store (Redis, sharded by region) + routing (contraction hierarchies on road graph) + ETA (historical + real-time ML) — each is a separate system; the interview tests whether you know how they compose."

---

*Full chapter: ~2,500 lines. Pairs with Ch64 (Recommendation/Ranking) for ETA ML models.*
