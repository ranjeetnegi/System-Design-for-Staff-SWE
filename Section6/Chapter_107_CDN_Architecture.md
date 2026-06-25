# Chapter 107: CDN Architecture — How a CDN Actually Works

> "Put it behind a CDN" is L4 thinking. L6 knows how the CDN works internally: PoP placement, anycast routing, cache hierarchies, origin shield, edge compute, and what happens on a cache miss at 10 million requests per second.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                    CDN ARCHITECTURE AT-A-GLANCE                     ║
╠══════════════════════════════════════════════════════════════════════╣
║  PROBLEM: Serve static and dynamic content to users globally         ║
║  with sub-20ms latency, high availability, and minimal origin load.  ║
╠══════════════════════════════════════════════════════════════════════╣
║  SCALE NUMBERS                                                        ║
║  Cloudflare:  450+ PoPs, 250+ Tbps capacity, 50M HTTP reqs/sec      ║
║  Akamai:      340,000+ servers in 4,100+ PoPs across 135 countries  ║
║  AWS CloudFront: 450+ PoPs (edge locations), 13 regional caches     ║
║  Fastly:      88 PoPs, ~1.5 Tbps capacity per major PoP             ║
╠══════════════════════════════════════════════════════════════════════╣
║  KEY COMPONENTS                                                       ║
║  Edge PoP → Origin Shield (mid-tier) → Origin Server                ║
║  Anycast routing → BGP selects nearest PoP for each user            ║
║  Cache hit ratio: 90–99% for typical static-asset workloads         ║
║  Origin offload: 95% hit ratio → origin sees only 5% of QPS         ║
╠══════════════════════════════════════════════════════════════════════╣
║  LATENCY TARGETS                                                      ║
║  Cache HIT at edge PoP:   1–5 ms                                    ║
║  Cache MISS → origin shield → origin: 50–200 ms                     ║
║  No CDN, cross-continent: 100–300 ms                                 ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Part 1: The Physics Problem CDNs Solve

The speed of light in fiber optic cable is approximately 200,000 km/sec — about two-thirds the speed of light in a vacuum. A network packet traveling from London to Sydney (16,000 km) has a theoretical minimum one-way latency of 80ms. Round-trip minimum: 160ms. In practice, with routing hops and queuing delays, a London–Sydney round trip is 250–300ms. For a user watching a video or loading a web page, this latency is perceptible and frustrating.

The CDN solution is elegant: instead of sending data from a distant origin to a user's browser, pre-position copies of the content at servers geographically close to users. A CDN PoP (Point of Presence) in Sydney serves Australian users with sub-5ms latency. The London origin only needs to serve the Sydney PoP occasionally when content is not cached — and the PoP serves millions of Australian users from that single copy.

The second problem CDNs solve is origin scalability. A major news site publishes a breaking story and receives 10M concurrent readers. Without a CDN, those 10M requests hit the origin servers simultaneously — a traffic spike that would require enormous pre-provisioned capacity. With a CDN, 99% of those requests are served from the edge cache. The origin handles only the 1% of cache misses, reducing its effective load from 10M to 100K requests. This is the "origin offload" benefit: the ratio of traffic the CDN absorbs versus what reaches the origin.

CDNs serve two categories of content with different strategies. **Static content** (images, CSS, JavaScript, video segments, fonts) is highly cacheable — the same bytes are served to every user. TTLs can be long (hours to years for versioned assets). **Dynamic content** (API responses, personalized HTML, authenticated pages) varies per user and cannot be naively shared. For dynamic content, CDNs act more as a TLS terminator and DDoS shield, with edge compute for customization, rather than a simple cache.

**Intern level:** "A CDN caches files closer to users to reduce latency." **Junior Engineer:** "CDNs have data centers (PoPs) around the world. Users connect to the nearest PoP instead of the origin." **Mid-level Engineer:** Knows cache hit ratios, TTLs, and can set up CloudFront or Cloudflare for a static site. **Senior Engineer:** Designs cache key strategy, understands origin shield, handles cache invalidation for deploys, calculates origin offload savings. **Staff Engineer:** Designs multi-CDN strategy, handles edge compute placement decisions, reasons about anycast vs unicast trade-offs, analyzes the blast radius of a CDN provider outage (Fastly 2021).

**Brainstorming Q1: Why can't you just put the origin server in every region instead of using a CDN?**
A: You could — and some systems do (active-active multi-region). But it's far more expensive and complex. You'd need to replicate all data to every region (consistency problem), handle cross-region writes (latency + conflict), and manage dozens of origin deployments. A CDN is asymmetric: you only push static assets to the edge, not your entire database. The origin remains the single source of truth. CDN PoPs are stateless caches — they hold no user data and require no database replication. This makes CDN deployment orders of magnitude simpler than a true multi-region origin. CDN + single-region origin is the right choice for most systems. True multi-region (with full data replication) is warranted only when origin availability requirements exceed what a single region can provide (99.99%+ SLA, regulatory requirements for data residency in specific countries).

**Brainstorming Q2: At what point does a CDN cache hit ratio stop improving?**
A: Cache hit ratio plateaus when the working set of content is fully represented in the CDN cache and TTLs are long enough to serve requests before expiry. For a static website with versioned assets (e.g., `app.abc123.js`), you can achieve 99%+ hit ratio because: (1) assets are versioned (URL changes on each deploy, so no stale content), (2) TTL is infinite (1 year), and (3) the total working set is small (megabytes). For dynamic content, hit ratio plateaus at 0% (every response is unique). For semi-dynamic content (product pages, category pages), hit ratio typically plateaus at 60–80% because: (1) the long tail of pages is rarely accessed (low chance of a cache hit), (2) personalization fragments the cache (same URL has different content for different users without cache partitioning), (3) prices and inventory change frequently (short TTLs, more misses). Improving beyond the plateau requires: longer TTLs with smarter invalidation, segment caching (cache the page without personalized sections, inject personalization client-side), or pre-warming the cache before publishing new content.

---

## Part 2: Points of Presence (PoPs) — Placement and Capacity

A PoP is a physical facility containing CDN servers, switches, and network equipment. PoPs are co-located in carrier-neutral facilities (Equinix, Digital Realty) or in major IXPs (Internet Exchange Points). Co-location at IXPs allows CDN servers to directly peer with hundreds of ISPs — data never travels the public internet from the CDN to the user's ISP.

**PoP placement strategy:** CDN providers place PoPs based on three factors: (1) **user density** — where users are concentrated (top metro areas account for 80% of internet traffic), (2) **peering opportunities** — IXPs where many ISPs interconnect (Amsterdam's AMS-IX, London's LINX, São Paulo's IX.br are critical), (3) **regulatory requirements** — some countries require data to stay within borders (China requires special licenses; Russia has SORM requirements; India has data localization laws for financial data). A CDN without a PoP in China must route Chinese users through a PoP outside China — typically Singapore or Tokyo — adding 50–100ms latency.

**Tier structure:** Cloudflare and Fastly use a flat (single-tier) model: every PoP connects directly to origin on cache miss. Akamai and AWS CloudFront use a hierarchical (two-tier) model: edge PoPs connect to regional shield PoPs on miss, and shield PoPs connect to origin. The two-tier model better for long-tail content with low hit rate at individual edge PoPs (the shield aggregates misses and serves them from a smaller, warmer cache).

**PoP capacity design:** A single PoP must handle the burst traffic for all users in its coverage area. Capacity is measured in Gbps (network throughput) and requests/second. A PoP serving a major metro area might need: 10–50 Gbps network capacity, 10,000–100,000 servers (distributed across the PoP's server racks), 100TB–1PB of SSD storage for cached content. CDN operators keep ~30% headroom above peak to handle traffic spikes and failover from adjacent PoPs.

**PoP failover:** When a PoP becomes unavailable (hardware failure, fiber cut, DDoS target), BGP anycast routes users to the next-nearest PoP. BGP convergence takes 30–180 seconds. During convergence, some users experience connection timeouts or errors. This is why the Fastly outage in June 2021 — caused by a bug triggered by a single customer's configuration change — knocked out GitHub, NYT, Reddit, and others for ~1 hour: all of those sites shared the same Fastly PoPs, and Fastly's anycast routes withdrew simultaneously worldwide.

**Intern level:** "PoPs are server locations." **Junior Engineer:** "PoPs are placed in major cities to reduce latency to users." **Mid-level Engineer:** Knows IXP peering, the difference between edge and regional caches. **Senior Engineer:** Designs PoP capacity planning for a CDN deployment, handles multi-region failover. **Staff Engineer:** Evaluates CDN providers by PoP density in target markets, designs multi-CDN traffic steering for 99.99% availability.

**Brainstorming Q1: How would you design a PoP placement strategy for a CDN targeting Latin American users?**
A: Start with traffic concentration data: Brazil accounts for ~50% of Latin American internet traffic (São Paulo is the critical PoP), followed by Mexico (Mexico City), Argentina (Buenos Aires), Colombia (Bogotá), and Chile (Santiago). Each of these cities has a major IXP — Brazilian Internet Exchange (IX.br) in São Paulo is the largest in the southern hemisphere by traffic. A CDN targeting Latin America must peer at IX.br and establish PoPs in São Paulo, Mexico City, and Buenos Aires as the tier-1 deployment. Secondary markets (Bogotá, Santiago, Lima) can be served from tier-1 PoPs with tolerable latency (50–100ms) until user volume justifies a local PoP. China and India-style regulatory complexity is limited in Latin America, though Brazil's LGPD (data protection law similar to GDPR) requires careful handling of personal data. The underserved edge cases are Central America, Ecuador, and Venezuela — often served from Miami (US city close to Latin America, massive peering hub at the NAP of the Americas).

**Brainstorming Q2: A PoP is overloaded during a flash crowd event. What happens?**
A: When a PoP is overloaded, several things happen in sequence: (1) request queue builds up → response latency increases → users experience slow loading, (2) if latency exceeds health check thresholds, the CDN's global load balancer starts routing some traffic to adjacent PoPs (this is traffic shedding, not full failover), (3) if the PoP has autoscaling, new servers spin up within 3–5 minutes, (4) if the overload is sustained, the PoP may gracefully withdraw its BGP routes for new connections while serving in-flight requests. Flash crowd overloads at edge PoPs rarely cause complete outages because CDNs typically have 30%+ headroom. The more dangerous failure mode is cache invalidation during a flash crowd: if you purge the cache right when 10M users are hitting the same URL, all of them simultaneously miss → stampede to origin. Always stagger cache invalidations during high-traffic events and use stale-while-revalidate.

---

## Part 3: Anycast Routing — How Users Find the Nearest PoP

Anycast is a network routing technique where multiple servers share the same IP address. When a user sends a packet to an anycast IP, the internet's BGP routing protocol delivers it to the "nearest" server (by AS-hop count), not a specific server. Every CDN PoP announces the same IP prefix via BGP. Users automatically connect to the closest PoP without any DNS-based steering.

**How anycast works step by step:**
1. CDN assigns an anycast IP block (e.g., 104.16.0.0/12 for Cloudflare).
2. Every PoP peers with local ISPs and exchanges BGP routes for that IP block.
3. When a user's ISP performs BGP route selection for 104.16.x.x, it selects the route with the lowest AS-path length — typically the geographically closest PoP.
4. The user's TCP connection is established to the nearest PoP. Every packet in the connection goes to the same PoP (BGP routes are stable for established connections).
5. If the PoP fails and withdraws its BGP announcement, the user's ISP re-routes to the next-nearest PoP after BGP convergence (30–180s). Established TCP connections break; new connections go to the surviving PoP.

**Anycast vs DNS-based routing (unicast):** AWS CloudFront and some CDNs use DNS-based steering — a DNS query for `d1234.cloudfront.net` returns the IP of the nearest edge location. DNS TTL of 60 seconds allows steering to change. Anycast is generally lower-latency because it works at the routing level (sub-millisecond), whereas DNS-based routing requires a DNS round trip before the first HTTP connection. Anycast is also more robust during PoP failures (no DNS TTL wait for failover).

**Anycast for DDoS mitigation:** A DDoS attack sending 1 Tbps of traffic to a CDN's anycast IP distributes the attack across all PoPs proportionally by how many users are near each PoP. No single PoP receives the full 1 Tbps. This is why Cloudflare can absorb 2+ Tbps DDoS attacks that would destroy any single data center — the attack is diffused across 450+ PoPs worldwide.

**Anycast drawback — TCP state:** Since anycast routes can change between connections (and theoretically mid-connection on route flap), TCP state must be handled carefully. CDNs ensure BGP route stability for existing connections. For UDP-based protocols (HTTP/3 uses QUIC over UDP), QUIC's Connection IDs allow the connection to survive a route change (IP address migration is built into QUIC). This is one advantage of HTTP/3 over HTTP/2 for CDN edge serving.

**Intern level:** "CDN uses DNS to point users to the closest server." **Junior Engineer:** "Anycast means multiple servers share one IP; BGP routes users to the nearest one." **Mid-level Engineer:** Understands BGP route withdrawal for PoP failover, DNS TTL implications. **Senior Engineer:** Designs PoP failover SLA with anycast convergence time in mind. **Staff Engineer:** Evaluates anycast vs DNS-based steering trade-offs for a new CDN product.

---

## Part 4: Cache Hierarchy — Edge, Shield, and Origin

A two-tier cache hierarchy dramatically reduces the number of cache misses that reach the origin server. Without a mid-tier, every edge PoP must independently fetch content from the origin on a miss. With a mid-tier (origin shield), misses from all edges in a region converge at one shield PoP, and the shield has a much higher hit rate than any individual edge (because it aggregates requests from hundreds of edge PoPs).

```
Single-tier (flat) CDN:
  User → Edge PoP A → [miss] → Origin
  User → Edge PoP B → [miss] → Origin   (separate origin request for same content)
  User → Edge PoP C → [miss] → Origin

Two-tier (hierarchical) CDN:
  User → Edge PoP A → [miss] → Shield → [miss] → Origin
  User → Edge PoP B → [miss] → Shield → [hit!] (served from shield, not origin)
  User → Edge PoP C → [miss] → Shield → [hit!]
```

**Origin shield hit rate:** For content with a CDN edge hit rate of 80% (20% of requests miss the edge), a shield serving 100 edge PoPs aggregates 100 independent 20% miss streams. If the shield has 5,000 objects and receives 100× more requests than any single edge PoP, it achieves much higher hit rate — typically 90–95%. The origin now receives only 1–2% of total requests instead of 20%. This is the key benefit: **the shield is warmer than any individual edge PoP because it sees more traffic**.

**AWS CloudFront origin shield:** CloudFront's origin shield is a single additional caching layer between the regional edge caches and the origin. Enabled per distribution. You select the region closest to your origin. CloudFront routes all cache misses from regional edge caches through the shield before hitting the origin. This reduces origin load by 60–80% for typical distributions.

**Cloudflare Tiered Caching:** Cloudflare's equivalent. Upper-tier caches in major cities serve as shields for surrounding edge PoPs. Enabled in the CDN settings. Cloudflare calls the upper tier "parent" caches and lower tier "child" caches.

**Cache hierarchy for video:** Video segment files (.ts files for HLS, .m4s for DASH) are large (2–10 MB), long-lived (TTL = infinite for immutable segments), and very hot when a live event is in progress. Without a shield, a popular live stream with 1M concurrent viewers can generate enormous origin bandwidth. With a shield: all edges in a region fetch from the shield on miss; the shield fetches from origin once per segment per region; origin serves only 20–30 shield PoPs instead of 450+ edge PoPs.

**Brainstorming Q1: When should you NOT use an origin shield?**
A: Origin shield adds latency to cache misses (extra hop). If your content is already highly cacheable (99%+ hit rate), the shield's marginal hit rate improvement is small while it consistently adds 10–30ms to the 1% of requests that miss the shield and reach origin. For highly dynamic content (personalized API responses with TTL=0), the shield adds latency without any caching benefit. Also, for very small deployments (5–10 edge PoPs in one region), the origin can typically handle the consolidated miss load directly. Shield is most valuable when: (1) origin is expensive to scale, (2) you have many geographically distributed edge PoPs with relatively low individual hit rates, (3) content is moderately cacheable (50–90% hit rate).

**Brainstorming Q2: A cache miss at the edge takes 200ms. The CDN's SLA is P99 < 50ms. How do you fix this?**
A: 200ms cache miss latency comes from: edge→shield round trip (~10ms) + shield→origin round trip (~50ms) + origin processing time (~100ms) + response serialization (~40ms). To hit 50ms P99 for ALL requests, you cannot accept 200ms misses — even at 1% miss rate, P99 will be dominated by misses. Solutions: (1) Increase cache hit rate by extending TTLs and using more aggressive caching policies (accept slightly stale content). (2) Reduce origin processing time: optimize database queries, add application-level caching, reduce response size. (3) Pre-warm the cache before known traffic spikes (product launches, scheduled events). (4) Accept that a P99 of 50ms means 99% of requests hit the cache — design the product around this (show loading states for cache misses, pre-fetch likely next pages). (5) For critical high-traffic pages that must always be under 50ms: serve stale with background refresh (stale-while-revalidate), accepting slightly stale content over high latency.

---

## Part 5: Cache Keys — What Makes Content Cacheable

The cache key determines which requests share a cached response. A poorly designed cache key causes: cache fragmentation (too many variants, low hit rate), cache poisoning (wrong variant served to wrong user), or privacy leaks (one user's personalized content served to another).

**Default cache key: URL.** A request for `https://cdn.example.com/images/logo.png` has cache key `https://cdn.example.com/images/logo.png`. All users requesting the same URL get the same cached response. This works perfectly for immutable static assets.

**Cache key normalization:** The same URL can arrive in many forms: `?a=1&b=2` and `?b=2&a=1` are semantically identical but different strings. CDNs normalize cache keys by: (1) lowercasing the URL, (2) sorting query parameters alphabetically, (3) stripping marketing parameters (`?utm_campaign=...`, `?fbclid=...`). Without normalization, `?a=1&b=2` and `?b=2&a=1` miss each other's cache entries even though the response is identical.

**The Vary header:** When the origin sends `Vary: Accept-Encoding`, it tells the CDN that the response varies based on the `Accept-Encoding` request header. The CDN stores separate cache entries for gzip-compressed and uncompressed variants. `Vary: Accept-Language` means a separate cache entry per language. `Vary: Cookie` means a separate cache entry per cookie value — catastrophic for cache hit rate (effectively disables caching, since every user has a unique cookie). Never send `Vary: Cookie` for publicly cacheable content.

**Cache partitioning for semi-personalized content:** A product page `/product/123` is mostly the same for all users but has a small personalized section (recommended products, cart count). Two strategies: (1) **Edge-Side Includes (ESI):** Cache the main page; for the personalized fragment, the edge makes a separate request per user (or uses a user segment cookie to look up a cached personalized fragment). (2) **Client-side injection:** Serve the static page from CDN cache; inject personalized content client-side via JavaScript (fetch personalization API after page load). Strategy 2 is simpler and more common; strategy 1 gives better initial render performance.

**Cache poisoning:** An attacker crafts a request with a special header that causes the CDN to cache a poisoned response and serve it to all subsequent users. Example: `X-Forwarded-Host: evil.com` — if the origin uses this header to build absolute URLs in the response, and the CDN caches it under the normal URL key, all users receive a response with `evil.com` URLs. Prevention: (1) strip unrecognized headers at the CDN before forwarding to origin, (2) never use request headers in response body construction unless those headers are part of the cache key (Vary), (3) validate that cache key includes all dimensions on which the response varies.

**Intern level:** "Cache key is the URL." **Junior Engineer:** Knows about query string normalization. **Mid-level Engineer:** Handles Vary headers, strips marketing params from cache key. **Senior Engineer:** Designs cache key strategy for complex dynamic content, avoids cache poisoning. **Staff Engineer:** Audits CDN configuration for cache fragmentation and poisoning vectors; designs edge-personalization architecture.

---

## Part 6: TTL, Cache Invalidation, and Surrogate Keys

**TTL-based expiry:** Every cached object has a time-to-live. After TTL expires, the next request for that object fetches fresh content from the origin. CDN TTL is set via `Cache-Control` response headers from the origin: `Cache-Control: max-age=86400` (1 day), `Cache-Control: s-maxage=3600` (1 hour for CDN, using `s-maxage` to distinguish CDN TTL from browser TTL), `Cache-Control: no-cache` (must revalidate with origin on every request).

**Versioned URLs for static assets:** The best TTL for immutable assets is infinite (1 year). Use content-addressed filenames: `app.abc123.js` where `abc123` is a hash of the file content. When the file changes, the hash changes, the URL changes, and the old URL's cache entry naturally expires (never accessed again). New users get the new URL; old cached pages reference the old URL (which still works from CDN cache). This is how Webpack, Vite, and every modern bundler handles asset caching.

**Hard purge (instant invalidation):** When content changes and you need to immediately invalidate all cached copies, send a purge API call to the CDN. Cloudflare: `DELETE /zones/{zone_id}/purge_cache`. AWS CloudFront: `POST /2020-05-31/distribution/{id}/invalidation`. Hard purge propagates to all PoPs within 30–60 seconds. Cost: CloudFront charges $0.005 per invalidation path (first 1,000 free/month). Cloudflare includes unlimited purges on paid plans. Hard purge caveat: the CDN stampede. All edge PoPs expire their copies simultaneously. If the content is popular, all PoPs simultaneously miss → stampede to origin. Stagger with soft purge or stale-while-revalidate.

**Surrogate keys (cache tags):** A response can be tagged with logical identifiers: `Surrogate-Key: product-123 category-electronics`. When product 123 is updated, purge tag `product-123` — all cached responses tagged with `product-123` are invalidated across all PoPs. This allows purging by business entity rather than by URL. Fastly, Cloudflare (called "Cache Tags"), and Varnish support this. Akamai calls them "cache tags" too. Extremely useful for e-commerce: a product price change invalidates all product pages, category pages, and search results tagged with that product's ID.

**stale-while-revalidate:** The origin sends `Cache-Control: max-age=60, stale-while-revalidate=3600`. When the 60s TTL expires, the CDN serves the stale content immediately (zero additional latency for the user) while triggering a background re-fetch from the origin. If the background re-fetch succeeds within 3,600 seconds, the cache is refreshed. If the origin is down for up to 3,600 seconds, the CDN continues serving stale content. This pattern gives: (1) zero-latency cache refreshes from the user's perspective, (2) origin failure tolerance up to `stale-while-revalidate` duration.

**Soft purge (stale with background refresh):** Fastly's soft purge marks cached content as stale rather than deleting it. The next request for the stale content is served immediately from cache (low latency) while triggering a background origin fetch. Prevents stampedes; slightly stale content is acceptable for most use cases.

**Brainstorming Q1: A news site publishes a breaking story. How do you ensure it appears on the homepage within 1 minute, given the homepage has a 1-hour CDN TTL?**
A: Three options, each with trade-offs: (1) **Trigger a cache purge on publish.** The CMS sends a purge API call to the CDN when the story is published. The homepage is re-fetched from origin within 60 seconds. Risk: stampede if the homepage is extremely popular. Mitigate with stale-while-revalidate on the freshly fetched content. (2) **Shorten the TTL for content that changes frequently.** Set homepage TTL to 60s instead of 1 hour. Cache hit rate drops (60s window means origin sees ~100× more requests), but freshness is guaranteed within 60s. (3) **Use surrogate keys.** Tag the homepage cache entry with `tag:homepage`. When any story is published, purge `tag:homepage`. Cleanest solution: purge only what changed. Combines well with soft purge to avoid stampedes.

**Brainstorming Q2: After deploying a new version of the website, 5% of users see the old version for up to 1 hour. Why, and how do you fix it?**
A: This happens when the HTML page (which references JavaScript and CSS) has a 1-hour TTL and users who visited the site before the deploy received the old HTML from CDN cache. Their browser then fetches JS/CSS using the old (versioned) URLs — which still work from CDN cache — so they see the old version. Fix: (1) Use versioned HTML as well — not just versioned assets. When you deploy, the HTML URL doesn't change, so you must purge the HTML from CDN. Send a targeted purge for all HTML pages on each deploy. (2) Use a service worker that checks for updates and prompts users to refresh. (3) Use short TTLs for HTML (60s) and long TTLs for versioned assets (1 year). This limits the stale window to 60 seconds.

---

## Part 7: CDN for Video Streaming

Video is the dominant use case for CDN bandwidth. Netflix accounts for ~15% of global internet downstream traffic; YouTube accounts for ~11%. Both rely entirely on CDNs for delivery. Video delivery has unique requirements that differ from general static file serving.

**HLS and DASH segment structure:**
- **Manifest file** (`.m3u8` for HLS, `.mpd` for DASH): Lists all available quality levels and segment URLs. Updated every few seconds for live streams. TTL: 2–10 seconds for live (must be fresh), ~1 hour for VOD (content doesn't change once published).
- **Segment files** (`.ts` for HLS, `.m4s` for DASH): Fixed-duration video chunks (2–10 seconds). For VOD, segments are immutable once generated. TTL: 1 year (use versioned filenames). For live, segments are generated as the stream progresses. TTL: ~1 year (old segments remain cached indefinitely after generation).

**CDN caching strategy for video:**
- VOD segments: `Cache-Control: max-age=31536000, immutable`. CDN caches indefinitely. High hit rates (popular content cached at edge; rarely-watched content cached only at shield).
- VOD manifest: `Cache-Control: max-age=3600`. Cached but refreshed hourly. No need to invalidate for VOD.
- Live manifest: `Cache-Control: max-age=4, stale-while-revalidate=6`. Very short TTL (smaller than the manifest update interval). stale-while-revalidate prevents thundering herd when TTL expires.
- Live segments: `Cache-Control: max-age=31536000`. Segments are write-once; once a live segment is generated, it never changes.

**Byte-range requests:** A video player may request a specific byte range from a large file (e.g., seeking to 10:00 in a 2-hour movie). CDNs must support byte-range caching: cache the full file and serve any range from the cached copy. If the CDN only has a partial cached copy (from a previous byte-range request), it must decide whether to fetch the full file or only the requested range. Most CDNs use "large file optimization" — fetch and cache the full file on any miss, enabling future byte-range requests to be served entirely from cache.

**Chunked transfer for live streaming:** Live segments are generated in real time. The CDN edge may receive a request for a segment before the full segment has been written by the encoder. With chunked transfer encoding, the CDN starts forwarding bytes to the viewer as they arrive from origin — reducing live latency from 2× segment duration (full segment download) to near real-time.

**Netflix Open Connect:** Netflix built their own CDN (Open Connect) rather than using commercial CDNs. Netflix ISP partners install Open Connect Appliances (OCAs) in their data centers — physical servers managed by Netflix running Netflix's CDN software. Netflix pre-positions (pre-pushes) popular content to OCAs during off-peak hours using an internal tool called CODEC (Content Discovery and Distribution). 95%+ of Netflix traffic is served from OCAs co-located inside ISP networks — effectively zero egress cost. Commercial CDNs serve the remaining ~5% (new content not yet in OCA cache, small ISPs without OCAs).

---

## Part 8: Edge Compute — Cloudflare Workers, Lambda@Edge, Fastly Compute

Static caching is powerful but limited. Edge compute extends CDN capabilities to running programmable logic at PoP locations — enabling personalization, authentication, A/B testing, and dynamic content generation without returning to the origin.

**Cloudflare Workers:** JavaScript (or WebAssembly) code that runs at every Cloudflare PoP. Executes on every request before the cache is checked. Use cases:
- **A/B testing:** Randomly assign users to A/B groups at the edge. Serve different HTML variants from different cache keys.
- **Authentication:** Verify JWTs at the edge; reject unauthenticated requests before they reach the origin.
- **Request transformation:** Rewrite URLs, add headers, modify request bodies.
- **Personalization:** Read a user segment cookie, fetch personalized content from a KV store (Cloudflare KV), assemble the response at the edge.
- **Geographic routing:** Route users in different countries to different origins based on their IP geolocation.

Workers runtime: V8 Isolate per request (not a full Node.js process — no file system, no `require()`). Cold start: <1ms (much faster than Lambda's 100ms+ cold start). Execution limit: 50ms CPU time (10ms on free tier). Memory: 128 MB per isolate.

**Lambda@Edge:** AWS's edge compute for CloudFront. Four event points: Viewer Request (before cache), Viewer Response (after cache, before viewer), Origin Request (on cache miss, before origin), Origin Response (after origin, before cache). Use cases similar to Workers but with Node.js or Python runtime. Cold start: 100–500ms (much slower than Workers). Maximum execution time: 5 seconds (Viewer Request/Response), 30 seconds (Origin Request/Response). Lambda@Edge runs in 13 regional PoPs (not all 450+ edge locations — only regional edge caches).

**Fastly Compute@Edge:** WebAssembly runtime with Rust, Go, or JavaScript SDKs. True edge compute at all PoPs. Startup time <1ms (Wasm instantiation). More powerful than Workers (higher memory, longer execution).

**KV stores at the edge:** Edge compute is only useful if it has data to personalize with. CDN providers offer edge-adjacent key-value stores: Cloudflare KV (eventually consistent across all PoPs, 1-second replication lag), Cloudflare Durable Objects (strongly consistent, single geographic location, used for real-time collaboration), AWS DynamoDB Global Tables (accessible from Lambda@Edge).

**When NOT to use edge compute:** Edge compute adds complexity to what should be a simple caching layer. Don't use edge compute unless: (1) you need personalization that makes the full origin round trip unacceptable, (2) you need authentication/authorization closer to users, or (3) you need geographic routing logic. For most applications, caching static assets + letting dynamic requests pass through to origin is sufficient.

---

## Part 9: Multi-CDN Strategy

Relying on a single CDN is a single point of failure. The Fastly outage of June 2021 lasted ~1 hour and affected thousands of websites simultaneously because they all used Fastly as their only CDN. A multi-CDN strategy provides resilience, geographic optimization, and pricing leverage.

**Why use multiple CDNs:**
1. **Resilience:** If CDN A has an outage, route traffic to CDN B within seconds.
2. **Geographic optimization:** CDN A may have better PoP coverage in Europe; CDN B has better coverage in Southeast Asia. Route users to the CDN with the best performance for their region.
3. **Pricing leverage:** Negotiating with CDN A is easier if CDN B is a viable alternative. Benchmark pricing regularly.
4. **Feature diversity:** CDN A may have better edge compute (Cloudflare Workers); CDN B may have better DDoS mitigation.

**Traffic steering approaches:**
1. **DNS-based routing:** A global DNS service (NS1, Dyn, Cloudflare Load Balancing) responds to DNS queries with either CDN A's CNAME or CDN B's CNAME based on: health checks, latency measurements, geographic rules. Failover time = DNS TTL (60–300 seconds). Simple but slow.
2. **Anycast-based routing:** Both CDNs announce the same IP block. BGP selects the closest (not easily steerable — you don't control BGP globally). Not practical for multi-CDN steering.
3. **Reverse proxy routing:** A primary CDN (e.g., Cloudflare) receives all traffic and, based on logic in Workers, routes to either CDN A backend or CDN B backend. Adds latency (double-CDN hop) but gives fine-grained control.
4. **Client-side selection:** The CDN provider's JavaScript SDK on the page measures latency to both CDNs in real time and selects the faster one for subsequent asset loads. Used by streaming providers for adaptive delivery.

**Real-user monitoring (RUM):** Measure actual user-experienced latency and availability for each CDN in each region. Beacon performance data from the browser (Resource Timing API) to a monitoring service. Use RUM data to drive CDN selection: if CDN A's p95 latency in APAC is 300ms vs CDN B's 80ms, route APAC users to CDN B.

**Configuration consistency:** The hardest part of multi-CDN is keeping cache invalidations, TTLs, and edge compute logic in sync across providers. Each CDN has a different API. Use a CDN abstraction layer (Terraform modules, CDN management tools like Fastly's multi-cloud control plane) to deploy configuration changes to all CDNs simultaneously.

---

## Part 10: Security at the CDN Layer

CDNs sit at the perimeter and are ideally positioned to absorb and filter attacks before they reach the origin.

**DDoS mitigation:** CDNs absorb volumetric DDoS attacks (SYN floods, UDP amplification, HTTP floods) using: (1) anycast absorption — attack traffic distributed across all PoPs; no single PoP is overwhelmed, (2) rate limiting — reject IPs exceeding N requests/second, (3) challenge pages — present a JavaScript/CAPTCHA challenge to suspected bots before allowing through, (4) IP reputation scoring — block IPs with known malicious history.

**WAF (Web Application Firewall) at the edge:** Cloudflare WAF, AWS WAF (with CloudFront), Fastly Next-Gen WAF. Inspects HTTP requests at the CDN PoP and blocks requests matching known attack patterns: SQL injection (`' OR 1=1`), XSS payloads (`<script>alert(1)</script>`), path traversal (`../../etc/passwd`), Log4Shell (`${jndi:ldap://...}`). WAF rules are updated centrally and propagated to all PoPs within minutes.

**TLS termination at the edge:** CDNs terminate TLS connections from users at the nearest PoP. The CDN-to-origin connection uses a separate TLS session (or private network peering). Benefits: (1) TLS handshake happens near the user (low latency), (2) origin does not need to manage TLS certificates for end users, (3) CDN handles certificate rotation automatically. For high-security use cases, use mutual TLS (mTLS) between CDN and origin to verify that requests actually came from the CDN (not directly from attackers trying to bypass the CDN's WAF).

**Certificate management:** CDN providers manage TLS certificates for customer domains. Cloudflare, CloudFront, and Fastly all provide free certificates via Let's Encrypt or their own CA, with automatic renewal. For custom certificates, upload your own. Certificate transparency logging (required for all public certificates) means your certificate issuance is publicly auditable.

**Bot management:** CDNs provide bot scoring (Cloudflare Bot Management, DataDome). Legitimate bots (Googlebot, Bingbot) are allowed; scrapers, credential stuffers, and inventory hoarders are challenged or blocked. Bot signals: User-Agent analysis, TLS fingerprinting (JA3), behavioral analysis (request rate, pattern, timing), IP reputation. Layered detection: good bots are identified by IP range + User-Agent; bad bots are flagged by behavioral anomalies and TLS fingerprint.

**Cache poisoning prevention (review from Part 5):** Normalize cache keys, strip attacker-controlled headers from cache key computation, never cache responses that vary on headers not in the Vary list, test your CDN configuration for cache poisoning using tools like Param Miner (Burp Suite extension).

---

## Part 11: CDN Configuration — Practical Settings

Understanding CDN configuration separates engineers who use CDNs from engineers who design CDN deployments.

**CloudFront example distribution configuration:**
```
Distribution settings:
  Origin: api.example.com
  Viewer Protocol Policy: Redirect HTTP to HTTPS
  Cache Policy: CachingOptimized (TTL: min=1s, default=86400s, max=31536000s)
  Origin Request Policy: CORS-S3Origin (forward Origin header, no cookies)
  Response Headers Policy: SecurityHeadersPolicy
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Content-Security-Policy: default-src 'self'
    - X-Content-Type-Options: nosniff
  Geo Restriction: Blocklist: Cuba, Iran, North Korea, Syria (OFAC)
  WAF: AWS WAF with AWSManagedRulesCommonRuleSet
  Logging: S3 bucket (access logs)
  Price Class: Price Class All (all PoPs)
```

**Cloudflare example cache rules (Page Rules or Cache Rules):**
```
Rule: *.example.com/assets/*
  Cache Level: Cache Everything
  Edge Cache TTL: 1 year
  Browser Cache TTL: 1 year
  Polish: Lossy (image optimization)
  Rocket Loader: On (async JS loading)

Rule: api.example.com/*
  Cache Level: Bypass
  Always Online: On (serve stale on origin error)
  Security Level: High
```

**Cache-Control header best practices by content type:**
```
# Versioned static assets (JS, CSS with content hash)
Cache-Control: public, max-age=31536000, immutable

# HTML pages (short TTL, CDN and browser)
Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=3600

# API responses (not cacheable, or short CDN cache)
Cache-Control: public, max-age=0, s-maxage=60, stale-while-revalidate=300

# Authenticated responses (NEVER cache on CDN)
Cache-Control: private, no-store

# Video manifests (live)
Cache-Control: public, max-age=4, stale-while-revalidate=6

# Video segments (VOD, immutable)
Cache-Control: public, max-age=31536000, immutable
```

---

## Part 12: CDN for Image Optimization

Images typically account for 60–70% of total page weight. CDNs can perform image optimization at the edge to reduce both bandwidth and latency.

**Format conversion:** Serve WebP (30% smaller than JPEG) or AVIF (50% smaller than JPEG) to browsers that support it. The CDN detects `Accept: image/webp` in the request and serves the WebP version, caching separately under the `Vary: Accept` dimension. Cloudflare Polish, Fastly's Image Optimizer, and Imgix do this automatically.

**Responsive images:** The CDN can resize images on-demand: `GET /images/hero.jpg?w=800&h=600&fit=cover` returns a 800×600 cropped version. The resized variant is cached at the CDN. The origin only needs to store the original full-resolution image. URL-based transformation parameters are part of the cache key (after normalization).

**Compression:** JPEG quality reduction from 100 to 80 is usually imperceptible but reduces file size by 50%. Cloudflare's "Lossless" mode converts PNG→WebP without quality loss. "Lossy" mode applies JPEG compression with quality 80. Automatic savings: 20–60% depending on the original quality.

**Lazy loading and Core Web Vitals:** CDNs can inject `loading="lazy"` attributes into images below the fold automatically (edge-side HTML transformation). Reduces initial page load and improves LCP (Largest Contentful Paint), a Core Web Vitals metric that Google uses for search ranking.

---

## Part 13: Cost Optimization with CDNs

CDNs cost money but can save more than they cost by reducing origin infrastructure requirements and egress costs.

**CDN pricing model:** CDN pricing has two components: (1) egress data transfer (cost per GB served from edge) and (2) HTTP request cost (cost per 10,000 requests). AWS CloudFront: $0.0085/GB in US, $0.12/GB in India, $0.0085/GB in Europe. First 1 TB/month free. Cloudflare: $0.00 egress on all plans (Cloudflare's business model is different — they profit from other services). Fastly: ~$0.12/GB in US.

**Break-even calculation:**
- Without CDN: origin egress to users. AWS EC2 to internet: $0.09/GB. 100 TB/month = $9,000 origin egress.
- With CloudFront: $0.0085/GB × 95 TB (CDN egress) + $0.09/GB × 5 TB (origin → CloudFront) = $807 + $450 = $1,257.
- Savings: $7,743/month. CDN subscription cost (if any) is far less than savings.

**Origin infrastructure savings:** With CDN absorbing 95% of traffic, the origin needs to handle only 5% of peak QPS. This can reduce origin server count by 10–20×. At $0.10/vCPU-hour, reducing from 100 servers to 10 servers saves ~$7,200/month.

**Compression and bandwidth reduction:** Enable Brotli compression (20–25% smaller than gzip for text) at the CDN layer. On 100 TB/month of JavaScript and CSS, Brotli can reduce bandwidth by 20 TB — saving ~$170/month at CloudFront pricing, much more at origin egress pricing.

---

## Part 14: The Fastly Outage — June 2021 Case Study

At 09:47 UTC on June 8, 2021, a significant portion of the internet went offline. GitHub, NYT, Reddit, Twitch, Spotify, Stack Overflow, BBC, Financial Times, and thousands of other sites returned errors or timed out. The cause: a single Fastly customer triggered a software bug with a routine configuration change.

**What happened:**
1. On May 12, 2021, Fastly deployed a new version of its software that contained an undiscovered bug — triggering a specific customer configuration setting would cause all PoPs in a region to crash simultaneously.
2. On June 8 at 09:47 UTC, a customer in the Asia-Pacific region changed a configuration setting that triggered the bug.
3. 85% of Fastly's global network became unavailable within ~60 seconds.
4. Fastly engineers identified the cause within 49 minutes and deployed a fix by 10:36 UTC.
5. Most CDN customers restored service by ~11:00 UTC (~73 minutes of downtime).

**Root cause:** Fastly's architecture used a global configuration push that deployed to all PoPs simultaneously. A single misconfiguration could impact all PoPs at once. The bug was latent for 26 days before being triggered.

**Lessons:**
1. **Single CDN = single point of failure.** Every site that relied only on Fastly went down. Multi-CDN architecture would have maintained availability.
2. **Configuration changes need canary deployments.** Fastly has since moved to incremental configuration rollouts (small % of PoPs first, then wider deployment) rather than global simultaneous pushes.
3. **CDN provider health checks.** Monitor your CDN independently from your CDN (i.e., don't use Fastly to check if Fastly is up). Use a separate synthetic monitoring service.
4. **Origin availability behind CDN.** Many sites had allowed direct origin access to be blocked (only CDN IPs allowed). This prevented fallback to origin even when origin was perfectly healthy.

**Post-incident Fastly changes:** Configuration change validation, staged rollouts, improved isolation between customer configurations, bug bounty for CDN configuration issues.

---

## Part 15: DB Schema — CDN Analytics Tables

While CDNs themselves don't require a schema you own, analytics pipelines ingesting CDN access logs do. Here is a production schema for CDN log analytics:

```sql
-- CDN access log events (partitioned by day)
CREATE TABLE cdn_access_logs (
    log_date         DATE NOT NULL,
    timestamp_utc    TIMESTAMP NOT NULL,
    pop_id           VARCHAR(20) NOT NULL,         -- e.g., 'IAD68' (Ashburn DC 68)
    client_ip        INET,
    client_country   CHAR(2),                       -- ISO 3166 country code
    client_asn       INTEGER,                       -- Autonomous System Number
    method           VARCHAR(10) NOT NULL,
    url              TEXT NOT NULL,
    cache_status     VARCHAR(20) NOT NULL,          -- HIT, MISS, EXPIRED, STALE, BYPASS
    status_code      SMALLINT NOT NULL,
    bytes_sent       BIGINT NOT NULL,
    response_ms      INTEGER NOT NULL,              -- Total response time in ms
    ttfb_ms          INTEGER,                       -- Time to first byte in ms
    origin_ms        INTEGER,                       -- Origin fetch time (NULL on HIT)
    tls_version      VARCHAR(10),                   -- TLSv1.3, TLSv1.2
    http_version     VARCHAR(10),                   -- HTTP/2, HTTP/3, HTTP/1.1
    user_agent       TEXT,
    referer          TEXT
) PARTITION BY RANGE (log_date);

CREATE INDEX ON cdn_access_logs (log_date, pop_id);
CREATE INDEX ON cdn_access_logs (log_date, cache_status);
CREATE INDEX ON cdn_access_logs (log_date, url);

-- Hourly rollups for dashboard performance
CREATE TABLE cdn_hourly_stats (
    hour_utc         TIMESTAMP NOT NULL,
    pop_id           VARCHAR(20) NOT NULL,
    cache_status     VARCHAR(20) NOT NULL,
    status_code      SMALLINT NOT NULL,
    request_count    BIGINT NOT NULL DEFAULT 0,
    bytes_sent       BIGINT NOT NULL DEFAULT 0,
    p50_ms           INTEGER,
    p95_ms           INTEGER,
    p99_ms           INTEGER,
    PRIMARY KEY (hour_utc, pop_id, cache_status, status_code)
);
```

---

## Part 16: CDN Configuration API Design

Key operations in a CDN management API:

```
# Create/update cache behavior
PUT /distributions/{id}/cache-behaviors
Body: {
  "pathPattern": "/assets/*",
  "ttlSeconds": 31536000,
  "compress": true,
  "cacheKeyPolicy": {
    "headers": [],
    "queryStrings": "none",
    "cookies": "none"
  }
}

# Purge by URL
DELETE /distributions/{id}/cache
Body: { "urls": ["/assets/app.123.js", "/images/hero.jpg"] }

# Purge by cache tag
DELETE /distributions/{id}/cache
Body: { "tags": ["product-123", "category-electronics"] }

# Get distribution metrics
GET /distributions/{id}/metrics?
  from=2024-01-01T00:00:00Z&
  to=2024-01-01T01:00:00Z&
  granularity=1m&
  metrics=requests,bytes,hit_rate,latency_p99

Response: {
  "data": [
    { "timestamp": "2024-01-01T00:00:00Z", "requests": 12450, "hit_rate": 0.97, "latency_p99_ms": 8 }
  ]
}
```

---

## Part 17: L5 vs L6 Calibration

| Dimension                  | L5 Answer (Senior SWE)                             | L6 Addition (Staff SWE)                                                        |
|----------------------------|----------------------------------------------------|--------------------------------------------------------------------------------|
| **What a CDN does**        | "Caches content near users, reduces latency"       | Specific: anycast routing, two-tier hierarchy, origin offload math             |
| **Cache hierarchy**        | "CDN has edge servers"                             | Edge → shield → origin; shield aggregation benefit; when to use each tier     |
| **Cache invalidation**     | "Send a purge request to CloudFront"               | Surrogate keys, stale-while-revalidate, avoiding stampede, soft vs hard purge  |
| **TTL strategy**           | "Set appropriate TTLs"                             | Versioned URLs for immutable assets, different TTLs per content type           |
| **Video streaming**        | "Use CDN for video"                                | HLS/DASH segment vs manifest TTL differences, live vs VOD strategies           |
| **Edge compute**           | "You can run code at the edge"                     | Cloudflare Workers vs Lambda@Edge trade-offs, KV store latency, isolation      |
| **Multi-CDN**              | "Use two CDNs for redundancy"                      | DNS-based vs proxy-based steering, RUM-driven routing, config sync challenges  |
| **Fastly outage lesson**   | "CDNs can go down"                                 | Multi-CDN strategy, configuration canary deployment, monitoring independence   |
| **Security**               | "CDN has WAF and DDoS protection"                  | Cache poisoning vectors, mTLS to origin, TLS fingerprinting for bot detection  |
| **Cost modeling**          | "CDN reduces origin costs"                         | Specific math: break-even at X GB/month, origin server savings, Brotli savings |

---

## Part 18: Pre-Interview Drill

Answer these in under 60 seconds each:

1. Explain anycast routing. Why does it make CDNs resilient to DDoS?
2. What is an origin shield? When does it dramatically reduce origin load?
3. A URL has `?b=2&a=1` and `?a=1&b=2`. Without cache key normalization, what happens?
4. Explain stale-while-revalidate. What is the latency impact vs regular TTL expiry?
5. Why should you never set `Vary: Cookie` on publicly cached content?
6. What is a surrogate key (cache tag)? Give a concrete e-commerce example.
7. What was the root cause of the Fastly outage in June 2021? What was the architectural lesson?
8. What is Cloudflare Workers? How does it differ from Lambda@Edge in cold start time?
9. Your CDN hit rate is 60%. What are three things you can do to increase it?
10. How do you verify that your CDN is actually caching content and not just passing requests through?
11. A product price changes. How do you invalidate all CDN-cached pages that show the old price?
12. What is cache poisoning? Give a concrete HTTP request example.

---

## Part 19: Common Interview Mistakes

1. **"Just put it behind a CDN" with no further thought.** This is the classic L4 answer. L5+ must explain: what gets cached, with what TTL, how invalidation works, how origin shield reduces load.

2. **Assuming all content is equally cacheable.** Authenticated responses (with session cookies) must never be cached at the CDN — sharing a response between users is a privacy breach. Always check whether a response contains user-specific data before setting a public TTL.

3. **Ignoring cache stampedes after invalidation.** "I'll just purge the cache on deploy" triggers simultaneous misses across all PoPs, all hitting the origin at once. Mitigate with stale-while-revalidate, soft purge, or pre-warming.

4. **Not knowing the Vary header.** `Vary: Accept-Encoding` is standard and safe. `Vary: Cookie` fragments the cache into as many entries as there are cookie combinations — effectively disabling caching. Know which headers to vary on and which to strip.

5. **Confusing browser cache and CDN cache.** `max-age=3600` sets browser TTL. `s-maxage=3600` sets CDN TTL without affecting browsers. They are different. Use `s-maxage` for CDN-specific TTLs when they differ from browser TTLs.

6. **Single CDN in the architecture.** For any system requiring 99.99%+ availability, a single CDN is a single point of failure. The Fastly 2021 outage affected even 99.9% SLA commitments. Multi-CDN is the answer.

7. **Not knowing the difference between edge compute and origin.** Edge compute (Workers, Lambda@Edge) runs at the CDN edge — great for lightweight transformations, authentication, and routing. It has memory limits, CPU limits, and no access to databases (only KV stores). Don't design a full business logic layer in edge compute.

---

## Part 20: Exercises

**Exercise 1:** You are deploying a SPA (Single Page App). The HTML is at `index.html` and assets are versioned (`app.abc123.js`, `styles.def456.css`). Design the CDN cache policy: what TTL for the HTML, what TTL for the assets, how do you handle a new deploy, and how do you prevent users from seeing the old version?

**Exercise 2:** A video streaming platform uses AWS CloudFront. Peak traffic is 1M concurrent viewers. The average bitrate is 4 Mbps. Calculate: (a) peak bandwidth at the CDN, (b) origin bandwidth assuming 95% cache hit rate, (c) monthly CDN egress cost at $0.0085/GB.

**Exercise 3:** Your CDN hit rate for a news homepage is 40%. Analyze three causes and propose specific fixes for each. What is the expected hit rate after each fix?

**Exercise 4:** Design a multi-CDN architecture using Cloudflare as primary and AWS CloudFront as backup. Specify: how traffic is normally routed, how failover triggers, how long failover takes, and how you keep CDN configurations in sync across both providers.

**Exercise 5:** Implement a Cloudflare Worker that: (1) adds a `X-Request-ID` header to every request, (2) blocks requests from countries in a configurable blocklist (read from a KV store), (3) adds response headers for security (HSTS, X-Content-Type-Options). Discuss the latency impact.

---

## Part 21: Homework

**Homework 1:** Set up a CloudFront distribution in front of an S3 bucket serving static assets. Configure: (a) versioned asset caching (1-year TTL), (b) HTML caching (5-minute TTL), (c) HTTPS redirect, (d) a cache invalidation script for deploys. Measure the hit ratio after 1 hour of traffic using CloudFront access logs.

**Homework 2:** Read the Fastly incident report from June 2021 (available on the Fastly blog). Write a 1-page analysis: (a) what the root cause was, (b) what Fastly should have done differently in their software deployment process, (c) what the affected websites should have done in their CDN architecture.

**Homework 3:** Experiment with cache key normalization. Set up a small CDN test (Cloudflare free tier or CloudFront with a small distribution). Make requests with query parameters in different orders and observe whether they result in separate cache entries or share one entry. Document the behavior and the configuration change needed to normalize.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                     CDN ARCHITECTURE KEY TAKEAWAYS                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  Anycast routing: multiple PoPs share one IP; BGP routes to nearest. ║
║  DDoS is absorbed across 450+ PoPs — no single point overwhelmed.   ║
║                                                                      ║
║  Cache hierarchy: edge (hot) → shield (aggregated misses) → origin. ║
║  Shield at 95% hit ratio → origin sees only 1-2% of total QPS.     ║
║                                                                      ║
║  Cache key: URL + normalized query params. Strip Vary: Cookie.       ║
║  Use surrogate keys (cache tags) for entity-level invalidation.      ║
║                                                                      ║
║  stale-while-revalidate: zero-latency refreshes + origin failure     ║
║  tolerance. Prevents stampedes on TTL expiry of popular content.     ║
║                                                                      ║
║  Video: manifest TTL=4s (live) or 1h (VOD); segment TTL=1 year.     ║
║  Versioned segments are immutable — cache indefinitely.              ║
║                                                                      ║
║  Fastly 2021: single CDN = single point of failure. Use multi-CDN   ║
║  with DNS-based failover (60s) or proxy routing (instant).           ║
║                                                                      ║
║  Edge compute: Workers (<1ms cold start, 50ms CPU limit);            ║
║  Lambda@Edge (100–500ms cold start, 5–30s limit). Pick by latency.  ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

---

## Part 22: Origin Offload — The Math

Understanding the quantitative benefit of a CDN is critical for making architectural decisions and justifying costs.

**Cache hit ratio definition:** `hit_ratio = CDN hits / (CDN hits + CDN misses)`. A hit ratio of 0.95 means 95% of requests are served from CDN cache; 5% reach the origin.

**Origin QPS with CDN:**
```
Example:
  Total user requests:     100,000 RPS
  CDN hit ratio:           95%
  CDN hits:                95,000 RPS  (served from edge, never reach origin)
  CDN misses to origin:     5,000 RPS  (actual origin load)

Without CDN: origin serves 100,000 RPS
With CDN:    origin serves   5,000 RPS  → 20× reduction in origin QPS
```

**Two-tier effect (with origin shield):**
```
  Total user requests:     100,000 RPS
  Edge hit ratio:           90%   (10,000 RPS miss the edge)
  Shield hit ratio:         70%   (of 10,000 edge misses, 7,000 hit shield)
  Origin hit ratio:         30%   (3,000 RPS reach origin)
  
  Effective origin load:    3,000 RPS  → 33× reduction vs no CDN
  vs single-tier CDN:       10,000 RPS (10×)
  
  Shield adds 3.3× additional origin offload for this workload.
```

**When shield helps most:** Content with moderate edge hit ratio (60–85%) benefits most from a shield. If edge hit ratio is already 99%+, the shield adds little. If edge hit ratio is below 50%, the shield's own hit rate may still be low enough that origin load remains high.

**Storage sizing:** A CDN PoP must cache enough content to serve its coverage population. Rule of thumb: cache the "hot" content that accounts for 80% of requests. For a news site with 100,000 articles, the top 1,000 articles account for ~80% of traffic (power law). Storing those 1,000 articles in cache (assuming 10 KB each = 10 MB) is trivial. For a video platform with 100M videos at 4 GB average size, caching the top 1% (1M videos = 4 PB) requires enormous edge storage — which is why video CDNs use shallow caches (only the most popular few thousand videos at each edge PoP, with deeper storage at shield PoPs).

**Bandwidth savings:**
```
  Monthly traffic:    1 PB = 1,000,000 GB
  CDN hit ratio:      95%
  CDN egress:         950,000 GB @ $0.0085/GB = $8,075 (CloudFront US)
  Origin egress:       50,000 GB @ $0.09/GB   = $4,500 (EC2→CloudFront is cheaper)
  Total CDN cost:     $12,575/month
  
  Without CDN (EC2→internet): 1,000,000 GB @ $0.09/GB = $90,000/month
  Net CDN savings:     $77,425/month
```

---

## Part 23: HTTP/3 and QUIC at the CDN Edge

HTTP/3 (based on QUIC, a UDP transport protocol) is increasingly standard at CDN edge PoPs. Understanding its benefits helps when explaining CDN performance to interviewers.

**The head-of-line blocking problem in HTTP/2:** HTTP/2 multiplexes multiple streams over one TCP connection. If a single TCP packet is lost, TCP's in-order delivery guarantee blocks all streams until the lost packet is retransmitted. This is TCP head-of-line blocking — a stream waiting for an unrelated stream's lost packet.

**QUIC (HTTP/3 transport) solves this:** QUIC implements stream multiplexing at the QUIC layer, above UDP. A lost UDP packet only blocks the specific QUIC stream it belongs to — other streams proceed independently. On lossy networks (mobile, intercontinental), HTTP/3 can be 20–40% faster than HTTP/2.

**QUIC at the CDN:** All major CDNs support HTTP/3: Cloudflare (since 2020), Fastly, AWS CloudFront (since 2022). HTTP/3 is negotiated via the `Alt-Svc: h3=":443"` header — the browser tries HTTP/3 on subsequent requests after seeing this header.

**0-RTT connection resumption:** QUIC supports 0-RTT for clients that have previously connected to the same server. On 0-RTT, the client sends the HTTP request in the very first packet — no handshake round trip needed. This is particularly valuable for CDN edge connections where users frequently reconnect (mobile users moving between networks). HTTP/2 over TLS 1.3 also supports 0-RTT (`early_data`), but 0-RTT carries a replay attack risk for non-idempotent requests.

**Connection migration:** QUIC connections are identified by a Connection ID, not by IP:port. When a mobile user switches from WiFi to 4G (IP address changes), a QUIC connection survives — the client and server negotiate a new path using the Connection ID. HTTP/2 over TCP would have broken the connection. This reduces reconnection overhead for mobile users at CDN edge PoPs by 1–3 RTTs.

**Deployment considerations:** QUIC requires UDP to be unblocked at firewalls. Some enterprise firewalls block UDP on port 443. CDNs fall back to HTTP/2 automatically when QUIC is blocked. Monitoring the QUIC/HTTP3 utilization percentage in CDN logs helps verify deployment effectiveness.

---

## Part 24: Advanced Cache Invalidation Patterns

**Surrogate key (cache tag) implementation details:** When the origin responds, it includes a `Surrogate-Key` header (Fastly) or `Cache-Tag` header (Cloudflare) listing all logical entities associated with the response:

```
HTTP/1.1 200 OK
Cache-Control: public, max-age=300
Surrogate-Key: product-789 category-shoes brand-nike
Content-Type: text/html
```

The CDN indexes this response under all three tags. A purge of tag `product-789` invalidates this and every other response tagged with `product-789` (the product detail page, the product in a category listing, the product in a search result, etc.).

**Write-through invalidation in e-commerce:** When a product price changes:
```
Application code:
  1. UPDATE products SET price = 49.99 WHERE id = 789
  2. COMMIT
  3. POST /cdn/purge { "tags": ["product-789"] }

CDN purges all pages cached with tag product-789:
  - /products/789            (product detail page)
  - /category/shoes          (lists product 789)
  - /search?q=nike+shoes     (search results containing product 789)
  - /homepage                (if 789 is a featured product)
```

This pattern ensures freshness without using short TTLs (which increase origin load).

**Event-driven CDN invalidation:** Instead of application code calling the CDN purge API directly, emit a `ProductUpdated` event to Kafka. A CDN invalidation service subscribes, resolves which cache tags to purge, and batches purge calls. This decouples the application from CDN knowledge, allows multiple CDNs to be purged in one place, and provides retry logic if the CDN purge API is temporarily unavailable.

**Distributed tracing for cache debugging:** When debugging unexpected cache misses, add trace headers: `X-Cache-Status: HIT` / `MISS`, `X-Cache-Hits: 3` (number of times this object has been served from cache), `Age: 120` (seconds since the cached object was fetched from origin). Most CDNs inject these headers automatically. Parse them in browser DevTools Network tab or server-side logs to verify cache behavior.

**Conditional requests (ETags and Last-Modified):** When a CDN object's TTL expires, the CDN can make a conditional request to the origin: `If-None-Match: "abc123"` or `If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT`. If the content hasn't changed, the origin returns `304 Not Modified` (no body) — saving bandwidth. The CDN refreshes the TTL and continues serving the cached object. This is especially valuable for large objects (images, video) that rarely change but have short TTLs.

---

## Part 25: CDN Architecture for a Global SaaS Application

Putting it all together: designing the CDN architecture for a B2B SaaS application (like Notion, Figma, or Slack) with global users.

**Content types and CDN strategy:**

| Content Type               | TTL       | Cache Level  | Invalidation Strategy        |
|----------------------------|-----------|--------------|------------------------------|
| App shell (index.html)     | 60 seconds| CDN + browser| Deploy-triggered purge       |
| Versioned JS/CSS bundles   | 1 year    | CDN + browser| None (versioned URL changes) |
| Static images/icons        | 30 days   | CDN + browser| None (version in URL)        |
| User-uploaded files        | 1 hour    | CDN only     | On file update/delete        |
| API responses (public)     | 30 seconds| CDN only     | Surrogate key purge on update|
| API responses (auth'd)     | No cache  | No cache     | N/A                          |
| WebSocket connections      | No cache  | Pass-through | N/A                          |

**Authenticated API bypass:** All API requests with session cookies or Authorization headers must bypass CDN cache (or use a private cache per user, which is effectively no caching for the CDN). Configure: `Cache-Control: private, no-store` on all authenticated endpoints.

**Origin selection:** Route API traffic to the origin region closest to the user. Use the CDN's geo-routing to send US users to us-east-1, EU users to eu-west-1, APAC users to ap-southeast-1. This reduces the origin processing latency on cache misses. Not possible if your application has only one region (in that case, CDN mitigates latency only for cached assets, not for API calls).

**Real-time features (WebSocket/SSE):** CDNs pass WebSocket and SSE connections through to the origin without caching. Some CDNs terminate WebSocket at the edge and relay (Cloudflare Tunnel, Ably's CDN integration). For most applications, real-time connections bypass the CDN and go directly to the origin, but the CDN still provides TLS termination and DDoS protection even for pass-through connections.

**Monitoring the CDN:**
- **Cache hit ratio** by path: ensure assets are being cached as expected. Unexpected misses indicate misconfigured TTLs or cache-bypassing headers.
- **Origin error rate**: sudden increase in origin errors seen by CDN = origin incident. CDN continues serving stale content (if `stale-if-error` is configured) — monitor for how long.
- **PoP-level latency**: P50/P95/P99 latency broken down by PoP and geographic region. Unexpected latency at a specific PoP indicates PoP-level issues.
- **Bandwidth by content type**: verify that large binary assets (images, video) dominate CDN egress, not HTML pages (which shouldn't have large responses).

---

## Part 26: CDN for Mobile Applications

Mobile apps have different CDN usage patterns than web apps.

**Static assets in mobile apps:** Mobile apps bundle most assets locally. CDN serves: app binary downloads (APK/IPA) from app stores (Apple's App Store CDN, Google Play's CDN), over-the-air (OTA) content updates (new game levels, product images, configuration files), API responses for non-personalized data (public price lists, product catalogs).

**API response caching for mobile:** Mobile users are often on slow or intermittent networks. Caching API responses at the CDN (for public endpoints) reduces latency and improves reliability during network transitions. Key pattern: `Cache-Control: public, max-age=60, stale-if-error=3600` — serve 60s-fresh content normally; serve up to 1 hour stale on origin errors.

**Offline-first and CDN:** Service Workers in mobile web apps (PWA) cache CDN-delivered assets locally in the browser. The layered caching strategy: CDN edge → browser → service worker cache → app display. On flaky mobile networks, the service worker serves from local cache even when the CDN is unreachable.

**Push notifications via CDN edge:** Some CDN providers (Cloudflare Push) support Web Push from edge Workers — send push notifications without returning to origin. Reduces push notification latency for time-sensitive applications (trading alerts, sports scores).

**Geographic content delivery for mobile:** Mobile apps often need region-specific content (country-specific pricing, language-specific content, geoblocked media). CDN geo-routing handles this: the CDN detects the user's country from IP geolocation and returns either region-specific content or a region-specific API endpoint. Store country code in the cache key if the response varies by country.

---

## Part 27: Designing a CDN from Scratch (Staff-Level Design Question)

"Design a simplified CDN" is a legitimate Staff-level system design question. Here is the complete answer:

**Requirements:** Serve static assets globally with < 20ms P99 for cache hits. Cache miss to origin < 200ms P99. Support cache invalidation in < 60 seconds. Handle 1M RPS globally.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTROL PLANE                               │
│  Config Service → distributes cache rules, origin config        │
│  Health Monitor → tracks PoP availability                       │
│  DNS Steering   → responds to DNS queries with nearest PoP IP   │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼───────────────────┐
            ▼                 ▼                   ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  PoP: US-East│  │  PoP: EU-West│  │  PoP: AP-SE  │
    │  200 servers │  │  150 servers │  │  100 servers │
    │  50 TB SSD   │  │  30 TB SSD   │  │  20 TB SSD   │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                  │                  │
           └──────────────────┼──────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  ORIGIN SHIELD    │
                    │  (US-East, primary)│
                    │  Aggregates misses │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  ORIGIN SERVERS   │
                    │  (Your S3/API)    │
                    └───────────────────┘
```

**PoP server design:** Each server in a PoP runs Nginx (or Varnish) as the caching proxy. Cache storage: NVMe SSD for hot content, RAM cache (ARC) for hottest content. Cache eviction: LRU + popularity weighting (items expiring soon but still popular are kept longer). Request routing within a PoP: consistent hashing ensures the same URL goes to the same server (maximizes cache hit rate within the PoP cluster).

**Cache invalidation pipeline:**
1. Customer calls purge API: `DELETE /cache { "url": "...", "tag": "..." }`
2. Invalidation service writes to Kafka topic `cdn-invalidations`
3. Each PoP has an invalidation consumer that reads from Kafka and marks cached objects as stale
4. Stale objects are served with `stale-while-revalidate` (still served immediately, background refresh triggered)
5. Propagation completes within 30 seconds across all PoPs (Kafka consumer lag typically < 5 seconds per PoP)

**DNS steering for nearest PoP:**
- Authoritative DNS server uses client IP geolocation to determine country/region
- Returns the anycast IP for the nearest PoP
- DNS TTL: 60 seconds (allows failover within 60 seconds if a PoP fails)
- Fallback: if nearest PoP is unavailable, return second-nearest PoP IP

**Health monitoring:**
- Each PoP sends heartbeat to the control plane every 5 seconds
- If a PoP misses 3 heartbeats, it's marked unhealthy
- DNS steering stops routing to unhealthy PoPs
- Alert fired to oncall within 30 seconds of PoP failure

**Scaling the origin shield:**
- Origin shield is a single logical entity but distributed across 3 active-active nodes
- Consistent hashing distributes URLs across shield nodes (same URL always goes to same node → higher hit rate)
- Shield nodes have 5× the storage of edge PoPs (aggregates traffic from all edges)

---

## Part 28: Comparison — Cloudflare vs Fastly vs AWS CloudFront vs Akamai

| Dimension              | Cloudflare               | Fastly                   | AWS CloudFront           | Akamai                   |
|------------------------|--------------------------|--------------------------|--------------------------|--------------------------|
| **PoP count**          | 450+                     | 88                       | 450+ (edge + regional)   | 4,100+                   |
| **Pricing model**      | Flat fee (free egress)   | Pay-per-GB + requests    | Pay-per-GB + requests    | Custom enterprise        |
| **Edge compute**       | Workers (V8, <1ms)       | Compute@Edge (Wasm)      | Lambda@Edge (Node/Python)| EdgeWorkers (JS)         |
| **Cache invalidation** | Tags (instant)           | Surrogate keys (instant) | Path-based (~60s)        | Fast Purge (5s)          |
| **DDoS protection**    | Included (Magic Transit) | Add-on                   | AWS Shield (add-on)      | Prolexic (add-on)        |
| **WAF**                | Included on Pro+         | Next-Gen WAF (add-on)    | AWS WAF (add-on)         | Kona Site Defender       |
| **Best for**           | Security, developer UX   | Performance-critical apps| AWS-native workloads     | Enterprise, media        |
| **Weakness**           | Workers JS only          | Fewer PoPs, higher cost  | Slow invalidation        | Complex, expensive       |

**When to pick each:**
- **Cloudflare:** Security-focused, excellent DDoS mitigation, best developer UX, free egress makes cost predictable. Best for: anything needing strong security + edge compute at reasonable cost.
- **Fastly:** Best programmatic CDN (most flexible VCL/Compute@Edge), excellent for media companies with complex caching logic. Best for: streaming video, highly customized caching rules.
- **AWS CloudFront:** Tight AWS integration (S3, ALB, API Gateway), pay-as-you-go, no contracts. Best for: AWS-native applications that want minimal vendor diversity complexity.
- **Akamai:** Largest network, best for global enterprises with complex geographic requirements and maximum availability SLAs. Best for: banks, governments, large media companies requiring 99.999% SLA.

---

## Part 29: L5 vs L6 Deep Dive — Cache Key Design

This is one area where the gap between L5 and L6 understanding is clearest.

**L5 scenario:** "We have a product page `/product/123`. Users in different countries see different prices due to currency. How do you handle this with a CDN?"

**L5 answer:** "We'd add the country to the URL: `/product/123?country=US`. The CDN caches separately per country."

**L6 answer:** The L6 engineer sees multiple problems with the query param approach and offers a complete solution:
1. **URL contamination:** Adding `?country=US` to every URL is ugly and breaks existing links.
2. **Cache key dimensions:** Use `Vary: CF-IPCountry` (Cloudflare's country header) or a custom geo header (`X-Geo-Country`) to partition the cache by country without URL changes. The CDN indexes one cache entry per country per URL.
3. **Country header injection:** Configure the CDN to inject `X-Geo-Country: US` based on IP geolocation. The origin uses this header to return the correct price. The CDN includes this header in the cache key.
4. **Cache fragmentation risk:** With 195 countries, each URL potentially has 195 cache entries. For a site with 1M product URLs, this is 195M cache slots — potentially exhausting cache storage. Solution: group countries into pricing tiers (US/EU/APAC/etc.) and use tier instead of raw country in the cache key. Reduces 195 variants to 5–10 pricing tier variants.
5. **Cache warming:** After a price change, purge by surrogate key and warm the most popular product pages for each pricing tier before the cached entry expires naturally.

This depth — identifying the fragmentation risk and proposing the tier grouping solution — is what distinguishes Staff-level thinking.

---

## Part 30: Pre-Interview Quick Reference

**The CDN request lifecycle (for any "walk me through" question):**
```
1. User's browser resolves cdn.example.com via DNS
   → CDN's anycast IP returned (nearest PoP)
2. TCP + TLS handshake with edge PoP (1–2 RTTs, ~5–20ms)
3. HTTP request arrives at edge PoP
4. Edge PoP checks local cache:
   HIT → return cached response (1–5ms total)
   MISS → continue to step 5
5. Edge PoP checks origin shield (if configured)
   Shield HIT → return, cache at edge (10–30ms total)
   Shield MISS → continue to step 6
6. Shield fetches from origin server (50–200ms total)
7. Origin processes request, returns response
8. Shield caches response (if cacheable)
9. Edge PoP caches response (if cacheable)
10. Response returned to user
```

**Key numbers to memorize:**
- Cache HIT latency: 1–5 ms
- Cache MISS + origin round trip: 50–200 ms
- CDN hit ratio for static sites: 95–99%
- CDN hit ratio for semi-dynamic: 60–80%
- Anycast BGP failover: 30–180 seconds
- DNS-based CDN failover: 60 seconds (DNS TTL)
- Surrogate key (cache tag) purge: 5–30 seconds
- CloudFront invalidation: ~60 seconds
- Cloudflare Workers cold start: < 1 ms
- Lambda@Edge cold start: 100–500 ms
- Brotli vs gzip compression: 15–25% smaller
- CDN egress (AWS US): $0.0085/GB
- CDN egress (self-hosted EC2→internet): $0.09/GB (10× more expensive)

---

```
╔══════════════════════════════════════════════════════════════════════╗
║               EXTENDED CDN KEY TAKEAWAYS                            ║
╠══════════════════════════════════════════════════════════════════════╣
║  Origin offload math: 95% hit rate → origin sees 5% of QPS.         ║
║  Two-tier (shield): 90% edge × 70% shield → origin sees 3% of QPS. ║
║                                                                      ║
║  HTTP/3 (QUIC): no TCP HOL blocking. 0-RTT resumption. Connection   ║
║  migration for mobile. Supported by Cloudflare, Fastly, CloudFront. ║
║                                                                      ║
║  Surrogate keys: purge by entity (product-789) not by URL. Scales   ║
║  to millions of pages sharing the same entity.                       ║
║                                                                      ║
║  Vary: Accept-Encoding = safe (gzip/br variants). Vary: Cookie =     ║
║  cache fragmentation disaster. Never use for public content.         ║
║                                                                      ║
║  Multi-CDN: DNS failover = 60s. Proxy routing = instant. Config      ║
║  sync = the hard operational problem. RUM drives routing decisions.  ║
║                                                                      ║
║  Design from scratch: PoP + shield + origin + Kafka invalidation +   ║
║  DNS steering + consistent hashing within PoP cluster.               ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Part 31: CDN Brainstorming Drills — Deep Questions

These are the harder questions an interviewer asks after you've described the basics.

**Q: "Your CDN hit ratio is suddenly 40% instead of the usual 95%. What do you investigate?"**

Step-by-step debugging approach:

1. **Check if it's a deployment event.** A new code deploy often involves cache-busted asset URLs (content hash in filename). During the transition period, new URLs have no cached entries. Expected hit ratio recovers as CDN warms. Check deploy timestamps against hit ratio graph.
2. **Check for a cache key change.** If someone changed the `Vary` header (e.g., adding `Vary: Accept-Language`), the CDN suddenly treats each language as a separate cache entry. All existing cache entries become misses until new language-segmented entries are populated.
3. **Check for cache header removal.** If the origin started returning `Cache-Control: no-store` (perhaps a misconfigured feature flag), CDN stops caching entirely. Verify by fetching a cacheable asset directly and inspecting response headers.
4. **Check for a TTL change.** If TTL was reduced from 300s to 10s, cache entries expire 30× faster. With the same traffic, fewer requests hit cached entries. Check recent CDN config changes.
5. **Check for a DDoS with cache-busting URLs.** An attacker requesting randomized URLs like `/static/app.js?bust=rand123` bypasses cache entirely. Check CDN logs for unusual query parameter patterns.
6. **Check for a new high-traffic endpoint.** If a new feature launched serving dynamic, non-cacheable content, total CDN requests went up but cached hits didn't. Hit ratio denominator grew; numerator didn't.

**Q: "How would you handle a celebrity tweet that sends 10 million requests to your CDN for a single image in 60 seconds?"**

This is the thundering herd + hot object problem.

First: CDN handles this naturally — it's designed for it. A single hot object in RAM at the edge PoP serves 10M requests without touching origin. The CDN itself is not the problem.

The problem is if the cache entry expires during the traffic spike, causing a stampede to origin. Solutions:

1. `stale-while-revalidate`: Serve the stale cached object while a single background request refreshes it. Only 1 request to origin during the refresh window regardless of incoming QPS.
2. Request coalescing at the edge: When an object is a cache miss, the CDN holds subsequent requests for the same URL and makes only a single request to origin. When origin responds, all queued requests receive the response simultaneously. Varnish calls this "request collapsing."
3. Lock-based coalescing: Similar to request coalescing but using explicit distributed locks. Less common at CDN layer but used for origin shield tier.

**Q: "You're designing a CDN for user-generated content (UGC) like profile photos. What are the specific challenges?"**

1. **Access control:** UGC may be private (profile visible only to friends). CDN cannot serve private content without authentication. Solution: signed URLs with expiry — the application generates a URL with an HMAC signature and TTL. CDN validates signature before serving. AWS CloudFront Signed URLs, Cloudflare Signed URLs.
2. **Content moderation:** Uploaded images might violate content policy. CDN serves content immediately after upload, but moderation runs asynchronously. A CDN rule can block serving until moderation passes: origin returns `403 Forbidden` for unmoderated content; application updates storage after moderation passes; CDN then serves normally.
3. **Long-tail caching:** UGC is long-tail — millions of objects each requested rarely. CDN can't cache all of them. Origin (S3) handles the tail; CDN caches only the popular subset. Set TTL based on content age: new uploads have shorter TTL (uploader might delete/replace); old stable uploads get longer TTL.
4. **EXIF stripping:** JPEG photos contain EXIF metadata including GPS coordinates (privacy risk). Strip EXIF at upload time or at the CDN edge via an edge worker before serving.
5. **Format conversion:** Not all users have WebP support. Edge workers can serve WebP to browsers that send `Accept: image/webp` and JPEG to others using the same origin URL. Reduces bandwidth 25–35% vs JPEG with no application changes.

---

## Part 32: CDN Security Deep Dive

**TLS at the CDN edge:** The CDN terminates TLS at every edge PoP. This means the CDN provider holds (or accesses) the TLS private key. For highly sensitive applications this creates a trust concern — the CDN provider can technically decrypt all HTTPS traffic. Alternatives:

- **mTLS to origin:** The CDN-to-origin connection uses mutual TLS so both sides authenticate. This doesn't prevent CDN from seeing plaintext, but it prevents spoofing of CDN traffic.
- **Keyless SSL (Cloudflare):** The private key stays on the origin's key server; the CDN sends TLS handshake data to origin to complete the handshake. CDN never sees the private key. Latency overhead: ~1 RTT per new TLS connection.

**DDoS mitigation at the CDN:**

- **L3/L4 DDoS (volumetric):** SYN floods, UDP floods, amplification attacks. CDN absorbs via large anycast network — attack traffic spreads across hundreds of PoPs. Each PoP rate-limits per source IP. Cloudflare's network capacity exceeds 200 Tbps, larger than any recorded DDoS attack.
- **L7 DDoS (application-layer):** HTTP floods targeting expensive endpoints. CDN WAF applies rules: rate limiting by IP, by user agent, by URL pattern. Challenge pages (CAPTCHA, JS challenge) distinguish humans from bots. Browser fingerprinting detects bot traffic patterns.
- **Slowloris:** Attacker opens many connections and sends headers slowly, holding connections open and exhausting origin connection pool. CDN handles this at the edge by enforcing connection timeouts (e.g., close connections idle for >30 seconds). Origin never sees Slowloris attacks because CDN handles connection management separately.

**Cache poisoning — OWASP CDN Security:**

- **HTTP request smuggling:** A discrepancy between how the CDN and origin parse chunked encoding or Content-Length headers can allow an attacker's request to "smuggle" a malicious request into the next user's response. Fix: use HTTP/2 between CDN and origin (no chunked encoding ambiguity).
- **Host header injection:** If the CDN passes the client's `Host` header to origin verbatim, a malicious `Host: evil.com` could trick the origin into generating a response with `evil.com` links — and the CDN caches it for all users. Fix: CDN validates and normalizes Host header before forwarding.
- **Web cache deception:** Attacker requests `/profile?/nonexistent.css` — the application returns the user's profile page, but if the CDN caches based on the `.css` extension in the URL, it caches the private profile page publicly. Fix: CDN must cache based on origin response headers (`Cache-Control`), not URL file extension.

---

## Part 33: Production Configuration Examples

**Nginx cache proxy with request coalescing:**
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=assets:50m max_size=50g inactive=60m;
proxy_cache_valid 200 304 5m;

location /static/ {
    proxy_pass http://origin;
    proxy_cache assets;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    proxy_cache_background_update on;
    proxy_cache_lock on;           # Request coalescing — hold concurrent misses
    proxy_cache_lock_timeout 5s;   # Give up waiting after 5s, pass directly to origin
    
    add_header X-Cache-Status $upstream_cache_status;  # HIT, MISS, STALE, UPDATING
}
```

**Cloudflare Worker — A/B test routing at edge:**
```javascript
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)
  
  // Check for existing experiment cookie
  const cookies = request.headers.get('Cookie') || ''
  const existingVariant = cookies.match(/ab_variant=([ab])/)?.[1]
  
  // Assign 50/50 split
  const variant = existingVariant || (Math.random() < 0.5 ? 'a' : 'b')
  
  // Route to different origins
  const origin = variant === 'a' 
    ? 'https://origin-a.example.com'
    : 'https://origin-b.example.com'
  
  const response = await fetch(origin + url.pathname + url.search, {
    headers: request.headers,
  })
  
  // Set variant cookie in response (30-day consistency)
  const resp = new Response(response.body, response)
  if (!existingVariant) {
    resp.headers.append('Set-Cookie',
      `ab_variant=${variant}; Max-Age=2592000; Path=/; SameSite=Lax`)
  }
  return resp
}
```

**CloudFront signed URL generation (Python):**
```python
from botocore.signers import CloudFrontSigner
from datetime import datetime, timedelta
import rsa

def create_signed_url(url: str, key_pair_id: str, private_key_pem: str,
                      expiry_hours: int = 1) -> str:
    def rsa_signer(message):
        private_key = rsa.PrivateKey.load_pkcs1(private_key_pem.encode('utf8'))
        return rsa.sign(message, private_key, 'SHA-1')
    
    signer = CloudFrontSigner(key_pair_id, rsa_signer)
    expiry = datetime.utcnow() + timedelta(hours=expiry_hours)
    
    return signer.generate_presigned_url(url, date_less_than=expiry)

# Returns URL like:
# https://d1234.cloudfront.net/private/photo.jpg
#   ?Expires=1735689600&Signature=...&Key-Pair-Id=K1234ABCD
```

**Event-driven CDN invalidation via Kafka:**
```python
# Producer side (in application service after DB write)
def on_product_updated(product_id: int, changed_fields: list[str]):
    event = {
        "event_type": "product_updated",
        "product_id": product_id,
        "changed_fields": changed_fields,
        "timestamp": time.time()
    }
    kafka_producer.send("cdn-invalidations", json.dumps(event).encode())

# Consumer side (CDN invalidation service)
def process_invalidation(event: dict):
    product_id = event["product_id"]
    
    # Resolve which cache tags to purge
    tags = [f"product-{product_id}"]
    
    # If price changed, also purge category and homepage featured slots
    if "price" in event.get("changed_fields", []):
        tags.extend([f"category-{cat}" for cat in get_product_categories(product_id)])
        tags.append("homepage-featured")
    
    # Batch purge across all CDN providers
    cloudflare.purge_by_tags(tags)
    fastly.purge_by_tags(tags)     # if multi-CDN
    
    metrics.increment("cdn_invalidations_sent", tags={"product_id": product_id})
```

---

## Part 34: Capacity Planning

**Estimating CDN cost for a social media app:**
```
Inputs:
  DAU:                       10M
  Sessions per DAU:           3
  Page views per session:     8   → 240M page views/day

Per page view CDN egress:
  HTML:       20 KB
  Images:    400 KB (5 images × 80 KB)
  API JSON:   80 KB (8 calls × 10 KB)
  JS/CSS:      0 KB (browser-cached on return visits, ~70% of sessions)

Average CDN egress per page view:
  0.3 × (170 KB) + 0.7 × (500 KB) = 51 KB + 350 KB = 401 KB

Total daily egress:
  240M × 401 KB = 96 TB/day = 2.9 PB/month

CDN cost comparison:
  Cloudflare Pro:   $200/month (unlimited egress, flat fee)
  CloudFront:       2,900 TB × $0.0085/GB = $24,650/month

Break-even: Cloudflare cheaper above ~24 TB/month.
```

**PoP storage sizing for a video platform:**
```
Total video library:        10M videos × 500 MB avg = 5 PB
Top 1% of videos (80% of views):
  100K videos × 500 MB = 50 TB needed per PoP

With 20 PoPs:
  Total edge storage:        20 × 50 TB = 1 PB
  Origin storage (S3):       5 PB
  Expected edge hit ratio:   ~80% (for cached titles)
  Expected origin QPS:       ~20% of total video requests
```

**Peak bandwidth per PoP:**
```
US total peak bandwidth:    400 Gbps
US East PoP serves 25%:     100 Gbps
Provisioned (with headroom): 150 Gbps
Servers at 10 Gbps NIC:     15 servers
With N+2 redundancy:         17 servers
```

---

## Part 35: Failure Runbooks

**Scenario 1: PoP outage (like Fastly 2021)**

Symptoms: Geographic region sees 503s. CDN status page shows PoP degraded.

Response:
1. Confirm scope: one PoP or all PoPs? If one PoP, anycast BGP will reroute within 30–180 seconds. No action required from application team.
2. If CDN-wide: prepare CDN bypass.
   - Pre-condition: DNS CNAME for `cdn.example.com` → ALB origin, TTL 60s
   - Update Route 53 record to point directly to origin ALB
   - Spin up additional origin capacity (CDN normally absorbs 95% of traffic)
   - Monitor origin error rates and latency
3. Communicate: status page update, customer notification if SLA breached.

**Scenario 2: Stale content after update**

Symptoms: Users see old prices/deleted items despite application update. CDN `Age` header shows large values.

Diagnosis steps:
```bash
# Inspect CDN response headers
curl -sI https://example.com/products/789 | grep -i 'cache\|age\|expires\|surrogate'

# Compare with direct origin
curl -sI https://origin.internal/products/789 | grep -i 'cache\|age\|expires'
```

Mitigation:
```bash
# Emergency purge via Cloudflare API
curl -X POST https://api.cloudflare.com/client/v4/zones/{zone}/purge_cache \
  -H "Authorization: Bearer {token}" \
  -d '{"tags": ["product-789"]}'

# Verify purge — Age should be 0 or missing
curl -sI https://example.com/products/789 | grep -i age
```

**Scenario 3: Cache hit ratio dropped 40% post-deploy**

Most likely cause: new deployment introduced cache-busted asset URLs. CDN warming takes ~15 minutes for high-traffic pages.

If hit ratio doesn't recover after 30 minutes: check for unintentional `Vary` header changes or `Cache-Control: no-store` on previously cacheable routes.

---

## Part 36: Comparison — Cloudflare vs Fastly vs CloudFront vs Akamai

| Dimension              | Cloudflare               | Fastly                   | AWS CloudFront           | Akamai                   |
|------------------------|--------------------------|--------------------------|--------------------------|--------------------------|
| **PoP count**          | 450+                     | 88                       | 450+                     | 4,100+                   |
| **Pricing model**      | Flat fee (free egress)   | Pay-per-GB + requests    | Pay-per-GB + requests    | Custom enterprise        |
| **Edge compute**       | Workers (V8, <1ms cold)  | Compute@Edge (Wasm)      | Lambda@Edge (100-500ms)  | EdgeWorkers (JS)         |
| **Cache invalidation** | Tags (5s propagation)    | Surrogate keys (instant) | Path-based (~60s)        | Fast Purge (5s)          |
| **DDoS protection**    | Included (200 Tbps+)     | Add-on                   | AWS Shield add-on        | Prolexic add-on          |
| **WAF**                | Included on Pro+         | Next-Gen WAF (add-on)    | AWS WAF (add-on)         | Kona Site Defender       |
| **Best for**           | Security, dev UX, cost   | Performance-critical     | AWS-native workloads     | Enterprise, media SLAs   |
| **Weakness**           | Workers JS only          | Fewer PoPs, higher cost  | Slow invalidation        | Complex, expensive       |

**When to pick each:**
- **Cloudflare:** Security-focused, best DDoS mitigation, free egress makes cost predictable at scale. Best for: security-sensitive + edge compute use cases.
- **Fastly:** Most flexible caching rules (VCL/Compute@Edge), excellent programmatic CDN. Best for: media streaming, highly customized caching rules.
- **CloudFront:** Tight AWS integration (S3, ALB, API Gateway), no upfront contracts. Best for: AWS-native applications wanting minimal vendor diversity.
- **Akamai:** Largest network, best for enterprises needing 99.999% SLA and global regulatory compliance. Best for: banks, governments, large media enterprises.

---

## Part 37: L5 vs L6 — Cache Key Design Deep Dive

This is one area where the gap between L5 and L6 understanding is clearest.

**L5 scenario:** "We have a product page `/product/123`. Users in different countries see different prices due to currency. How do you handle this with a CDN?"

**L5 answer:** "We'd add the country to the URL: `/product/123?country=US`. The CDN caches separately per country."

**L6 answer:** The L6 engineer sees multiple problems with the query param approach:

1. **URL contamination:** Adding `?country=US` to every URL is ugly and breaks existing links shared via email or social media.
2. **Cache key dimensions:** Use `Vary: CF-IPCountry` (Cloudflare's injected header) or `X-Geo-Country` to partition cache by country without URL changes. CDN indexes one cache entry per country per URL — no URL changes required.
3. **Country header injection:** Configure the CDN to inject `X-Geo-Country: US` based on IP geolocation before forwarding to origin. Origin uses this header to return the correct price.
4. **Cache fragmentation risk:** With 195 countries, each URL potentially has 195 cache entries. For a site with 1M product URLs, this is 195M cache slots — potentially exhausting cache storage and SSD IOPS.

   Solution: Group countries into **pricing tiers** (e.g., US, EU, LATAM, APAC, ROW) and use `X-Pricing-Tier` header instead of raw country. Reduces 195 variants to 5 pricing tier variants.

5. **Cache warming after price change:** After a global price change, purge by surrogate key `product-{id}` and proactively warm the most popular products for each pricing tier before TTL expires naturally, avoiding a miss storm.

This depth — identifying the fragmentation risk and proposing the tier grouping solution — is what Staff-level thinking looks like.

---

## Part 38: Pre-Interview Quick Reference

**The CDN request lifecycle:**
```
1. DNS resolution: cdn.example.com → anycast IP → nearest PoP
2. TCP + TLS handshake with edge PoP (1-2 RTTs, ~5-20ms)
3. Edge checks local cache:
     HIT  → return response (1-5ms total)
     MISS → check shield
4. Shield checks cache:
     HIT  → return to edge, cache at edge (10-30ms total)
     MISS → fetch from origin (50-200ms total)
5. Origin processes, returns response with Cache-Control + Surrogate-Key
6. Shield caches, edge caches, user receives response
```

**Numbers to memorize:**
```
Cache HIT latency:               1-5 ms
Cache MISS + origin:             50-200 ms
Two-tier origin offload:         edge 90% × shield 70% → origin 3% of traffic
Anycast BGP failover:            30-180 seconds
DNS failover:                    60 seconds (TTL bound)
Surrogate key purge:             5-30 seconds
CloudFront invalidation:         ~60 seconds
Cloudflare Workers cold start:   < 1 ms
Lambda@Edge cold start:          100-500 ms
CDN egress (CloudFront US):      $0.0085/GB
EC2→internet egress:             $0.09/GB  (10× more expensive)
Brotli vs gzip savings:          15-25% smaller
```

---

## Part 39: Review Checklist

Use before a Staff-level system design interview:

**Core concepts:**
- [ ] Anycast BGP routing → nearest PoP
- [ ] Two-tier cache (edge → shield → origin), quantify origin offload
- [ ] `max-age`, `s-maxage`, `stale-while-revalidate`, `stale-if-error` differences
- [ ] Surrogate key/cache tag purging vs URL purging
- [ ] Why `Vary: Cookie` is dangerous; how to use `Vary` correctly
- [ ] Cloudflare Workers vs Lambda@Edge (startup latency, language, isolation)
- [ ] Multi-CDN with DNS failover and proxy routing
- [ ] Cache poisoning vectors: Host header, request smuggling, web cache deception

**Quantitative:**
- [ ] HIT: 1-5ms. MISS: 50-200ms
- [ ] Two-tier offload: origin sees 3% of traffic
- [ ] DNS failover: 60s. Tag purge: 5-30s

**Staff-specific:**
- [ ] Cache key fragmentation risk (Vary × many values)
- [ ] Request coalescing prevents thundering herd at CDN layer
- [ ] Keyless SSL for compliance
- [ ] Kafka-based async CDN invalidation pipeline
- [ ] CDN cost: CloudFront $0.0085/GB vs EC2 $0.09/GB
- [ ] Multi-CDN RUM-based traffic steering
- [ ] Fastly 2021 outage: single BGP advertisement failure

---

## Part 40: Extended Exercises

**Exercise 6 (Staff-level design):** Design a CDN cache invalidation system for an e-commerce platform with 10M products, where product updates must reflect in all CDN-cached pages within 60 seconds. The platform has 100,000 product updates per minute at peak. Design: the event pipeline, tag indexing scheme, purge batching strategy, CDN API rate limit handling. Sketch the architecture.

**Exercise 7 (Failure analysis):** CDN hit ratio drops from 95% to 60% at 3 PM Tuesday. No PoP failures, normal traffic volume. Walk through every possible cause, diagnostic steps for each, ranked by likelihood.

**Exercise 8 (Cost modeling):** Choose between CloudFront ($0.0085/GB first 10 TB, $0.0080/GB next 40 TB) and Cloudflare Pro ($200/month flat). Your monthly egress is 50 TB. Calculate monthly cost for each and identify the break-even point.

**Exercise 9 (Edge compute):** Design a Cloudflare Worker that: (1) validates JWT in Authorization header, rejects invalid tokens with 401; (2) injects user tier (free/pro/enterprise) from JWT claims as `X-User-Tier` header to origin; (3) rate-limits free-tier users to 100 requests/minute using Workers KV. Write pseudocode or actual Worker JavaScript.

**Exercise 10 (Multi-CDN):** You run Cloudflare (80% primary) + Akamai (20% backup). Both pull from the same origin. Describe: (1) simultaneous cache invalidation across both CDNs; (2) consistent cache keys so both cache same object versions; (3) detection and failover from Cloudflare to Akamai; (4) avoiding double-caching costs.

---

## Part 41: Reference Architecture Summary

```
┌────────────────────────────────────────────────────────────────────┐
│                   CDN COMPLETE ARCHITECTURE                        │
└────────────────────────────────────────────────────────────────────┘

USER REQUEST
    │
    ▼
DNS RESOLUTION (anycast → nearest PoP IP)
    │
    ▼
EDGE PoP (e.g., Chicago)
├── TLS termination (keyless SSL optional)
├── DDoS / WAF filtering (L3/L4 + L7)
├── Edge function (Workers / Lambda@Edge)
│   └── Auth, A/B test, geo routing, rate limit, EXIF strip
├── Cache lookup
│   ├── HIT → return immediately (1-5ms total)
│   └── MISS → forward to shield
│
▼
ORIGIN SHIELD (US-East-1)
├── Second-tier cache
│   ├── HIT → cache at edge, return
│   └── MISS → fetch from origin
│
▼
ORIGIN (Application Servers / S3)
├── Compute response
├── Set Cache-Control, Surrogate-Key headers
└── Return → shield → edge → user

INVALIDATION PATH (asynchronous):
    DB write (application)
        │
        ▼
    Kafka topic: cdn-invalidations
        │
        ▼
    Invalidation Service
    ├── Resolves surrogate keys → URL set
    ├── Calls CDN purge APIs (Cloudflare, Akamai)
    └── Retries with exponential backoff on rate limit
    
Propagation: 5–30 seconds across all PoPs

CACHE KEY DECISIONS:
  Include:  URL path, normalized Accept-Encoding, pricing-tier (not country)
  Exclude:  Cookie, User-Agent, full Accept-Language, Authorization
  
TTL STRATEGY:
  Versioned assets (/app.a1b2c3.js):    1 year
  Semi-stable pages (/product/123):     5 min + surrogate key purge
  Highly dynamic (/feed):               no-cache or 30s max
  User-specific (/dashboard):           no-cache, bypass CDN entirely
```

---

## Part 42: Additional Brainstorming — 5-Level Progression

**INTERN:** "What is a CDN?" A content delivery network caches copies of your files in data centers closer to users so they download faster. Instead of everyone in Tokyo fetching your files from your US servers, Tokyo users fetch from a CDN PoP in Japan.

**JUNIOR:** Understands cache HIT vs MISS. Knows that static assets (JS, CSS, images) should be served from CDN. Can configure CloudFront origin with an S3 bucket. Knows TTL controls how long content stays cached.

**MID:** Understands two-tier hierarchy (edge + shield). Can design cache key strategy for the application. Knows surrogate keys / cache tags for fast purging. Understands `Vary` header risks. Can choose between URL versioning and cache invalidation.

**SENIOR:** Identifies the right TTL for each content type. Designs CDN bypass strategy for dynamic APIs. Sets up proper monitoring (hit ratio by route, origin error rate). Considers edge compute for auth or routing logic. Knows how CDN affects TTFB and Core Web Vitals.

**STAFF:** Designs origin offload math to justify CDN investment. Identifies cache key fragmentation risks and pricing-tier grouping. Designs multi-CDN with RUM-based traffic steering. Architects Kafka-based async invalidation pipeline decoupled from application code. Knows CDN security failure modes (cache poisoning, Vary header attacks). Can design a CDN from scratch for an interviewer.

---

## Part 43: Brainstorming Q&A — Set 1

**Q: "How does TLS resumption work at CDN edge PoPs and why does it matter for performance?"**

TLS session resumption allows a client to reconnect without a full 2-RTT handshake. Two mechanisms:

- **TLS session tickets:** Server sends an encrypted session token; client presents it on reconnect. Server decrypts and resumes without looking up session state. Problem at CDN scale: tickets are encrypted with a session key. If the client reconnects to a different PoP server, that server needs the same session key — so session keys must be synchronized across all servers in the PoP cluster. Cloudflare calls this "Keyless Session Resumption" — session keys distributed via their internal key distribution protocol.
- **TLS 1.3 0-RTT:** Client uses early data from a previous session. First request is sent in the same packet as the handshake — zero round trips to start the application request. Risk: 0-RTT data can be replayed. CDNs disable 0-RTT for non-safe HTTP methods (POST, PUT, DELETE) and only allow it for GET/HEAD.

Why it matters: mobile users reconnect frequently (WiFi → 4G transitions). TLS resumption saves 1–2 RTTs per reconnect — ~50–150ms on typical mobile networks. At 1M sessions/day, this is billions of saved milliseconds across the user base.

**Q: "A new engineer on your team asks why we can't just increase all CDN TTLs to 7 days for better cache hit ratios. How do you explain the trade-offs?"**

Increasing TTLs does improve hit ratio — up to a point. But the trade-offs are significant:

1. **Stale data window:** With a 7-day TTL, a price error on your e-commerce site serves wrong prices for up to 7 days before the cache naturally expires. Even with surrogate key purging, you must purge correctly on every update — any missed purge results in a week of incorrect data.

2. **A/B test contamination:** If you run an A/B test that changes your homepage layout, users might see the old layout for up to 7 days (if they hit a PoP that cached the old version before the test started and hasn't been purged).

3. **Emergency rollbacks:** If you deploy a security fix that removes a vulnerable endpoint, a 7-day TTL means CDN continues serving the vulnerable response for up to 7 days unless you explicitly purge.

4. **Cache storage pressure:** Very long TTLs mean objects age out more slowly, consuming cache storage. Objects that are no longer popular sit in cache for 7 days rather than being evicted by LRU pressure.

The right approach: use long TTLs only for truly immutable content (versioned assets with content hashes in the URL). For mutable content, use shorter TTLs (5–30 minutes) combined with surrogate key purging to handle updates immediately.

---

## Part 44: Brainstorming Q&A — Set 2

**Q: "Explain how a CDN handles HTTP/2 server push and whether it helps CDN caching."**

HTTP/2 Server Push allows the server to proactively send resources (JS, CSS, fonts) along with the initial HTML response, before the browser has parsed the HTML and requested them. Example: when serving `/index.html`, the server pushes `/app.js` and `/style.css` in the same HTTP/2 connection.

At the CDN layer, server push is complicated:
- The CDN terminates HTTP/2 from the client. HTTP/2 push must happen at the edge (CDN), not at the origin (which has no direct connection to the client).
- Cloudflare Workers and some CDNs support edge-initiated pushes — the Worker reads the HTML and proactively pushes anticipated resources. But the CDN must have the pushed resources in its cache.
- For a cache HIT: CDN can push cached resources alongside the HTML. Net win: browser gets critical resources ~1 RTT earlier.
- For a cache MISS: CDN can't push resources it doesn't have yet. No benefit until resources are cached.

In practice, HTTP/2 push has largely been superseded by `<link rel="preload">` (which signals to the browser to preload resources) and HTTP/3 with 0-RTT. Chrome removed HTTP/2 server push support in January 2022 after finding it rarely helped in practice. Modern CDN best practice is `103 Early Hints` — the CDN returns a `103` response with `Link: </style.css>; rel=preload` before the full response is ready, letting browsers start fetching resources during origin processing time.

**Q: "How do you handle CDN for an API that has both public (cacheable) and authenticated (non-cacheable) endpoints at the same domain?"**

The most common production pattern:

1. **URL-based routing at CDN:** Configure CDN rules: `if URL starts with /api/public/ → cache`. `if URL starts with /api/ (default) → no cache, pass-through`.
2. **Response-header-based:** Origin sets `Cache-Control: public, max-age=60` on public endpoints and `Cache-Control: private, no-store` on authenticated endpoints. CDN respects these headers and only caches public responses.
3. **Separate domains (preferred by some teams):** `api.example.com` (authenticated, bypasses CDN entirely). `public-api.example.com` (public read-only, CDN-fronted). Cleaner mental model — no risk of accidentally caching an auth'd endpoint. Downside: two API base URLs in client code.

The critical mistake to avoid: accidentally caching authenticated responses. This happens when a developer adds `Cache-Control: max-age=300` to an endpoint for performance and forgets it returns user-specific data. Mitigation: CDN rule that ignores `Cache-Control: max-age` if the request contains an `Authorization` header or a session cookie. Configure explicitly: `if request has Authorization header → do not cache regardless of Cache-Control`.

---

## Part 45: War Stories

**Pinterest hot partition (2014):** Pinterest CDN served a mix of user photos and static assets. When a pin went viral (millions of repins in hours), all requests went to the same CDN PoP that first cached it. That PoP was consistently 10× more loaded than other PoPs. Root cause: CDN's DNS-based load balancing was geographic — viral US content loaded to US East PoP, which then received all subsequent US East traffic for that viral content. Fix: CDN provider added content-distribution hashing so viral objects were replicated across all US PoPs within minutes of high QPS being detected.

**Cloudflare routing leak (2010):** Cloudflare misconfigured a BGP filter, allowing malicious routes to propagate that redirected traffic for several major websites through unexpected PoPs. Users experienced slowdowns (content served from geographically distant PoPs) but no data exposure. Lesson: CDN BGP routing changes need strict pre-flight testing and staged rollout; a routing table error affects all PoPs simultaneously.

**GitHub's Fastly dependency (2020):** GitHub experienced a major outage when Fastly had a regional incident. GitHub had architected their serving stack with Fastly as a required dependency (not just a cache acceleration layer). When Fastly degraded, GitHub degraded. Post-incident fix: GitHub redesigned serving so Fastly is "in the path" for acceleration but not for availability — origin serves all traffic if CDN is unavailable, even though it's slower. CDN as cache layer, not gatekeeper.

**NPM CDN thundering herd (2018):** npm registry serves package metadata. A popular package release caused 100K+ CI pipelines to simultaneously fetch the new version. npm's CDN hadn't cached the new version yet (just published). 100K simultaneous origin requests for the same object in < 1 second. Origin buckled. Fix: npm pre-warms CDN for new major package releases by proactively pushing to multiple PoPs immediately on publish.

---

## Part 46: One-Liners for Interview Recall

- **"CDN = physics solution"** — network latency from speed of light; CDN puts a copy of the data near the user.
- **"Shield = cache for the cache"** — origin shield aggregates misses from all edge PoPs into a single second-tier cache.
- **"Surrogate keys = purge by entity, not URL"** — one product update purges every page mentioning that product.
- **"Vary: Cookie = cache fragmentation bomb"** — one Vary value per unique cookie = no effective caching.
- **"stale-while-revalidate = serve fast, refresh in background"** — users never wait for a cache refresh.
- **"Request coalescing = thundering herd killer"** — 1000 simultaneous misses → 1 origin request.
- **"Lambda@Edge cold starts are 100–500ms; Workers cold starts are sub-millisecond"** — choose based on latency sensitivity.
- **"Multi-CDN = DNS failover (slow) or proxy routing (fast)"** — for instant failover, proxy routing is required.
- **"Never Vary on Authorization or Cookie for public content"** — effectively disables CDN caching.
- **"CDN egress is 10× cheaper than EC2 egress"** — always CDN for high-egress workloads.
- **"Fastly 2021: one BGP route advertisement brought down half the internet"** — single points of failure exist even at CDN scale.
- **"HTTP/3 (QUIC) at edge: no TCP head-of-line blocking, 0-RTT resumption, connection migration"** — critical for mobile CDN performance.

---

## Part 47: Additional Reference Numbers

| Metric                                   | Value                          |
|------------------------------------------|--------------------------------|
| Edge cache HIT latency                   | 1–5 ms                         |
| Cache MISS + origin (typical)            | 50–200 ms                      |
| CDN PoP count (Cloudflare)               | 450+                           |
| CDN PoP count (Akamai)                   | 4,100+                         |
| Typical edge cache hit ratio (static)    | 95–99%                         |
| Typical edge cache hit ratio (semi-dyn)  | 60–80%                         |
| Shield additional origin offload         | 2–4×                           |
| Anycast BGP failover time                | 30–180 seconds                 |
| DNS-based CDN failover                   | 60 seconds (TTL bound)         |
| Surrogate key purge propagation          | 5–30 seconds                   |
| CloudFront invalidation time             | ~60 seconds                    |
| Cloudflare Workers cold start            | < 1 ms                         |
| Lambda@Edge cold start                   | 100–500 ms                     |
| HTTP/3 improvement on lossy networks     | 20–40% faster than HTTP/2      |
| Brotli compression improvement vs gzip   | 15–25% smaller                 |
| WebP vs JPEG size reduction              | 25–35% smaller                 |
| AVIF vs JPEG size reduction              | 50% smaller                    |
| CDN egress cost (CloudFront US)          | $0.0085/GB                     |
| EC2 internet egress cost                 | $0.09/GB (10× CDN)             |
| Cloudflare Worker memory limit           | 128 MB                         |
| Cloudflare Worker CPU time limit         | 50 ms per request              |
| Lambda@Edge max execution time           | 30 seconds (viewer request)    |
| DDoS protection capacity (Cloudflare)    | 200+ Tbps                      |

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                   KEY TAKEAWAYS — CDN ARCHITECTURE                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  PHYSICS PROBLEM: Speed of light is ~200km/ms. CDN solves this by   ║
║  caching content at PoPs close to users. 1-5ms edge hit vs 200ms    ║
║  cross-continent origin miss.                                        ║
║                                                                      ║
║  TWO-TIER HIERARCHY: Edge (local PoP) → Shield (regional) → Origin. ║
║  Edge 90% hit × Shield 70% hit → origin sees only 3% of traffic.    ║
║                                                                      ║
║  CACHE KEYS: Never Vary on Cookie/Authorization for public content.  ║
║  Vary by pricing tier (5 values), not country (195 values).          ║
║  Surrogate keys enable purge by entity, not URL.                     ║
║                                                                      ║
║  INVALIDATION: Kafka → CDN Invalidation Service → purge APIs.        ║
║  Decouples application from CDN. Enables batching + retry.           ║
║  Tag purge: 5-30s. CloudFront path invalidation: ~60s.               ║
║                                                                      ║
║  EDGE COMPUTE: Workers < 1ms cold start. Lambda@Edge 100-500ms.      ║
║  Use Workers for auth, A/B tests, geo routing, rate limiting.        ║
║                                                                      ║
║  SECURITY: Cache poisoning via Host header, request smuggling, web   ║
║  cache deception. Validate Host header. Use HTTP/2 CDN→origin.       ║
║  DDoS absorbed at anycast network (200+ Tbps capacity).              ║
║                                                                      ║
║  COST: CloudFront $0.0085/GB vs EC2 $0.09/GB. Cloudflare flat fee   ║
║  wins above ~24 TB/month. Always CDN for high-egress workloads.      ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Part 48: HTTP Caching Headers — Full Reference

Every engineer working with CDNs needs to memorize these headers precisely.

**`Cache-Control`** — the primary caching directive:

| Directive                        | Who it targets    | Meaning                                                      |
|----------------------------------|-------------------|--------------------------------------------------------------|
| `max-age=N`                      | Browser + CDN     | Cache for N seconds                                          |
| `s-maxage=N`                     | CDN only          | CDN cache duration (overrides max-age for shared caches)     |
| `no-store`                       | Browser + CDN     | Never cache anywhere                                         |
| `no-cache`                       | Browser + CDN     | Cache but revalidate before every use (must-revalidate)      |
| `private`                        | Browser only      | Browser can cache; CDN must not cache                        |
| `public`                         | Browser + CDN     | Explicitly cacheable (even if response has Set-Cookie)       |
| `stale-while-revalidate=N`       | CDN (+ Firefox)   | Serve stale for N seconds while refreshing in background     |
| `stale-if-error=N`               | CDN               | Serve stale for N seconds on origin error (5xx/timeout)      |
| `immutable`                      | Browser           | Don't revalidate within max-age (for versioned assets)       |
| `must-revalidate`                | Browser + CDN     | On expiry, must revalidate (no serving stale on error)       |

**`ETag`** — strong validator for conditional requests:
- Origin sets `ETag: "abc123"` on response
- Client sends `If-None-Match: "abc123"` on subsequent request
- Origin returns `304 Not Modified` if content unchanged (no body — saves bandwidth)
- CDN uses ETag for its own conditional fetch to origin on cache expiry

**`Last-Modified`** — weak validator:
- Origin sets `Last-Modified: Mon, 01 Jan 2024 12:00:00 GMT`
- Client sends `If-Modified-Since: Mon, 01 Jan 2024 12:00:00 GMT`
- Origin returns `304 Not Modified` if unchanged
- Less precise than ETag (1-second granularity) but widely supported

**`Vary`** — tells CDN which request headers affect the response:
- `Vary: Accept-Encoding` — safe: creates gzip and br variants. Standard on all compressible assets.
- `Vary: Accept-Language` — risky at scale: one cache entry per language per URL. Group into `X-Lang-Bucket: en/es/zh` first.
- `Vary: Cookie` — never for public content. Creates one cache entry per unique cookie value = infinite fragmentation.
- `Vary: Authorization` — never for public content. Same problem as Cookie.

**`Surrogate-Control`** (CDN-specific, not standard HTTP):
- `Surrogate-Control: max-age=3600` — CDN caches for 1 hour; browser uses `Cache-Control: no-store`
- Allows different CDN TTL vs browser TTL on the same response
- Fastly strips `Surrogate-Control` before forwarding to browser; origin sets both headers for different effects

---

## Part 49: CDN for Gaming and Real-Time Applications

Game developers use CDNs differently than web developers. Understanding these use cases broadens the interview discussion.

**Game asset delivery:** Game clients download patch files, textures, and audio — often GBs per update for millions of simultaneous players. CDN design considerations:
- **Peak bandwidth on patch day:** A major game update can spike to 10+ Tbps globally. Pre-announcement warming: game launchers silently prefetch patch packages days in advance.
- **Byte-range requests:** Players download only the changed portions of large files. CDN must support range requests: `Range: bytes=500000-999999`. CDN caches the full file and serves the range slice from cache — doesn't require a range request to origin.
- **Checksum validation:** Game launchers verify checksums (SHA-256) of downloaded files. CDN must not corrupt or alter file content — binary files don't tolerate transparent manipulation (unlike HTML where CDN might inject headers).
- **Cdn-on-the-edge for multiplayer:** Actual game session traffic (UDP packets for player positions) bypasses CDN — CDN is not designed for low-latency bidirectional UDP. CDN handles only asset download and configuration files. Game servers use direct UDP or WebRTC with STUN/TURN.

**Leaderboard and match history APIs:**
- Match history: cacheable with short TTL (1–5 minutes). Mostly read traffic, infrequent updates.
- Leaderboard top-100: cacheable (refreshed every 30 seconds). Not personalized.
- Player profile: partially cacheable — public stats cacheable; private inventory not cacheable.
- CDN rule: if `X-User-Id` header present → no cache. If anonymous request → cache with surrogate key.

**Live event streaming for gaming (Twitch-style):**
- HLS/DASH chunks served from CDN with very short TTL (2–4 seconds, matching chunk duration)
- Chunk TTL = chunk duration = slightly longer to allow multiple viewers the same chunk
- High cache hit ratio because all viewers of a popular stream request the same chunk seconds apart
- Origin shield critical: thousands of edge PoPs each making independent requests to origin per chunk = fan-out problem. Shield aggregates to single origin request per chunk.

---

## Part 50: CDN Observability — What to Monitor

A Staff engineer owns the CDN monitoring strategy, not just the CDN configuration.

**Metrics to collect:**

| Metric                          | Source           | Alert threshold                              |
|---------------------------------|------------------|----------------------------------------------|
| Cache hit ratio (by route)      | CDN access logs  | < 80% for static, < 50% for semi-dynamic     |
| Origin error rate               | CDN → origin     | > 1% error rate (5xx)                        |
| P99 TTFB (by PoP, by country)   | CDN metrics API  | > 500ms P99 for static assets                |
| CDN bandwidth (egress)          | CDN billing API  | Alert on 2× baseline (DDoS signal)           |
| Purge propagation latency       | Synthetic checks | > 60s for any tag purge                      |
| Edge Workers error rate         | Workers logs     | > 0.1% error rate (Workers code bugs)        |
| Origin shield hit ratio         | Shield metrics   | < 60% (shield not adding value)              |
| WAF blocked requests            | WAF logs         | Spike (potential DDoS)                       |

**Synthetic monitoring — the canary strategy:**
- Run a canary process every 60 seconds that fetches key URLs through the CDN and records `X-Cache-Status`, `Age`, and TTFB.
- If `X-Cache-Status: HIT` becomes `MISS` for a URL that should always be cached, alert immediately. (Possible TTL config regression.)
- If `Age` for a URL is > 24 hours, cache is not being purged on updates. Alert.
- Use multiple synthetic regions to monitor specific PoP behavior.

**CDN log pipeline:**
```
CDN access logs → S3 (every 5 minutes) → Lambda → Kinesis → 
  Elasticsearch (for ad-hoc queries) + 
  Prometheus metrics (for dashboards/alerts)

Key fields to extract:
  - cache_status (HIT/MISS/STALE/BYPASS)
  - url_path (for per-route hit ratio breakdown)
  - country_code (for geographic performance)
  - edge_pop (for PoP-specific health)
  - ttfb_ms (time to first byte)
  - response_size_bytes (for bandwidth attribution)
  - waf_action (ALLOW/BLOCK/CHALLENGE)
```

**SLO definition for CDN-fronted service:**
- **Availability SLO:** 99.99% of requests receive a non-5xx response (edge responses count; origin errors served as stale don't count as failures if stale-if-error is configured)
- **Latency SLO:** 95% of cached asset requests complete in < 50ms; 99% in < 200ms
- **Freshness SLO:** 99.9% of content is served within 60 seconds of last update (enforced by surrogate key purge + synthetic monitoring verification)

---

## Part 51: Staff-Level Decision Framework

When asked "should we use a CDN and how should we configure it?" — this is the decision tree:

```
1. Is the content publicly cacheable?
   └── No (user-specific, auth-gated) → CDN for TLS termination + DDoS only; no caching
   └── Yes → continue to step 2

2. How frequently does this content change?
   └── Never (versioned assets) → max-age=31536000, immutable
   └── Rarely (< once per hour) → s-maxage=3600, surrogate key for instant purge
   └── Frequently (> once per hour) → s-maxage=60, stale-while-revalidate=30
   └── Every request (real-time data) → no-store, CDN bypass

3. Does the response vary by user attribute?
   └── No variation → no Vary header
   └── Varies by encoding only → Vary: Accept-Encoding (safe)
   └── Varies by country/region → use X-Geo-Tier custom header (not raw country)
   └── Varies by user → Cache-Control: private (CDN doesn't cache)

4. Do you need edge compute?
   └── Auth validation → Workers/Lambda@Edge (check latency sensitivity)
   └── A/B testing → Workers (< 1ms) preferred over Lambda@Edge (100-500ms cold)
   └── Geographic routing → Workers or CDN-native geo rules
   └── Heavy compute (image resize) → origin or dedicated service; not edge

5. What's the blast radius of a stale-serving incident?
   └── Low (informational pages) → longer TTL acceptable, surrogate key optional
   └── High (prices, availability, security content) → short TTL + mandatory surrogate keys
   └── Critical (auth, permissions) → no-store, bypass CDN entirely
```

---

## Part 52: CDN and Core Web Vitals

Core Web Vitals are Google's user experience metrics used in search ranking. CDN architecture directly affects them.

**LCP (Largest Contentful Paint)** — time until the largest visible element renders. Typically the hero image or above-the-fold background image.
- CDN effect: serving the LCP image from edge cache (1–5ms) vs origin (50–200ms) directly reduces LCP by 45–195ms.
- Best practice: ensure the LCP image URL is cacheable, has a long enough TTL, and is not blocked by access controls that force origin fetches.
- Preconnect hints: `<link rel="preconnect" href="https://cdn.example.com">` in HTML tells the browser to establish a CDN connection early — saves TLS handshake RTT when the LCP image request happens.

**FID (First Input Delay) / INP (Interaction to Next Paint)** — time until the browser responds to user interaction. Affected primarily by JavaScript execution, not CDN. However:
- Serving compressed, minified JS bundles from CDN reduces parse time.
- Edge workers that delay the response (for auth, geo routing, A/B test) add to TTFB, which in turn pushes back when JS starts executing. Keep Workers fast (< 5ms processing).

**CLS (Cumulative Layout Shift)** — visual stability. Images without explicit width/height attributes cause layout shifts when they load.
- CDN can inject `width`/`height` attributes via image optimization edge Workers.
- Serving WebP/AVIF (smaller file) means images load faster → less time in layout-incomplete state.

**TTFB (Time to First Byte)** — not a Core Web Vital itself but directly drives LCP.
- CDN cache HIT: TTFB 1–5ms (excellent)
- CDN cache MISS + origin: TTFB 50–200ms (acceptable)
- No CDN, cross-continent: TTFB 200–800ms (poor for LCP threshold)

---

## Part 53: CDN Testing in CI/CD Pipeline

A Staff engineer adds CDN configuration testing to the deployment pipeline so regressions are caught before production.

**What to test in CI:**

1. **Cache header verification:** After deploying a new route, a CI job fetches the URL through a staging CDN environment and asserts:
   ```bash
   cache_control=$(curl -sI https://staging-cdn.example.com/api/public/prices | grep -i cache-control)
   assert_contains "$cache_control" "s-maxage=60"
   assert_contains "$cache_control" "stale-while-revalidate=30"
   ```

2. **No accidental caching of auth'd endpoints:**
   ```bash
   # Every authenticated endpoint must return Cache-Control: private or no-store
   curl -sI -H "Authorization: Bearer token" https://staging-cdn.example.com/api/me | \
     grep -i cache-control | grep -E 'private|no-store' || exit 1
   ```

3. **Surrogate key presence:**
   ```bash
   # Product pages must include surrogate keys for fast invalidation
   surrogate_key=$(curl -sI https://staging-cdn.example.com/product/123 | grep -i surrogate-key)
   assert_contains "$surrogate_key" "product-123"
   ```

4. **Cache hit verification after warm-up:**
   ```bash
   # First request warms cache; second request must be HIT
   curl -sI https://staging-cdn.example.com/static/app.css > /dev/null
   cache_status=$(curl -sI https://staging-cdn.example.com/static/app.css | grep -i x-cache)
   assert_contains "$cache_status" "HIT"
   ```

**Staging CDN environment:** Run a small CDN simulation (Nginx + proxy_cache, or a real Cloudflare Workers staging environment) in CI. Test all CDN configuration rules against actual HTTP responses from the staging application.

**Pre-deploy checklist:**
- [ ] All new public endpoints have `Cache-Control: public, s-maxage=N` set appropriately
- [ ] All new authenticated endpoints have `Cache-Control: private, no-store`
- [ ] All new product/content pages include `Surrogate-Key` header with entity IDs
- [ ] No new `Vary: Cookie` or `Vary: Authorization` headers on public content
- [ ] CDN worker code changes tested against staging for latency regression (< 5ms overhead)
- [ ] Invalidation pipeline tested: update entity in DB → purge event fired → synthetic check verifies CDN now returns new content

---

## Part 54: Homework — Deepening CDN Mastery

**Homework 1 — Read the source:** Read Cloudflare's blog post on "How we Delivered 100 Exabytes" and their writeup on the Fastly 2021 outage post-mortem. Both are publicly available. Note the failure modes and mitigations they describe.

**Homework 2 — Hands-on experiment:** Create a free Cloudflare account. Point a personal project's domain at Cloudflare. Enable caching for static assets. Use browser DevTools Network tab to observe `CF-Cache-Status: HIT` and `CF-Cache-Status: MISS` headers. Deliberately add `Cache-Control: no-store` to a route and verify Cloudflare respects it.

**Homework 3 — Write an edge Worker:** Using Cloudflare Workers (free tier), write a Worker that: (1) rejects requests without an `X-API-Key` header with 401; (2) adds `X-Request-Id` UUID to every request; (3) logs the request country to the Worker's console. Deploy and test.

**Homework 4 — Calculate your CDN break-even:** Estimate your current or last project's monthly egress volume. Calculate the monthly cost for CloudFront vs Cloudflare vs Fastly at that volume. Identify which is cheapest and under what conditions that changes.

**Homework 5 — Design the invalidation system:** Design (on paper or in a document) a CDN cache invalidation system for a multi-region e-commerce platform that: (a) invalidates CDN caches in < 30 seconds after a product update; (b) handles 50,000 product updates per minute at peak (sale events); (c) works across both Cloudflare and CloudFront simultaneously; (d) has a dead-letter queue for failed purges with manual retry UI. Sketch the architecture including Kafka topics, consumer groups, CDN API rate limits, and monitoring.

---

## Part 55: Interview Application — Using CDN Knowledge Naturally

The best Staff-level answers weave CDN knowledge in without making it the center of attention, unless the question is specifically about CDN.

**In a URL shortener design (like bit.ly):**
> "The redirect endpoint is 302→target URL. Since most links are hit many times, I'd put Cloudflare in front and cache the redirect response for 60 seconds with `Cache-Control: public, s-maxage=60`. This absorbs ~95% of redirect lookups without hitting the DB. For links that were updated or deleted, I'd invalidate by surrogate key `link-{short-code}`. The cache serves well for long-lived links; new links (not yet in cache) take a cold miss to the DB — acceptable since they're uncacheable until the first hit warms the edge."

**In a news feed design:**
> "The first-page API response (top 20 stories) can be lightly cached at CDN for 30 seconds with `stale-while-revalidate=30`. Even personalized feeds can have a shared 'trending stories' component that's CDN-cached. The authenticated wrapper is bypassed via `Cache-Control: private`, but the trending stories component is fetched as a public sub-request that CDN can cache separately — micro-caching at the CDN layer."

**In a payment system design:**
> "Payment endpoints never go through CDN cache. The checkout page HTML can be CDN-cached (public), but the payment processing API (`POST /payments`) has `Cache-Control: no-store` and bypasses CDN. What CDN does give us here is DDoS protection and TLS termination at the edge — valuable even without caching."

**Signaling depth to the interviewer:**
If the interviewer seems interested, volunteer one non-obvious detail: *"One thing I'd add is making sure the CDN cache key doesn't include the pricing tier in the URL but as a normalized header, to avoid cache fragmentation — 195 countries would create 195 cache entries per product page and exhaust SSD IOPS at the PoP."* This one sentence shows Staff-level awareness of a non-obvious operational concern.

---

## Part 56: CDN Chapter Statistics

This chapter covers the complete CDN architecture needed for Staff/L6 Google system design interviews. Topics covered:

- CDN fundamentals: physics problem, PoPs, anycast BGP routing
- Two-tier hierarchy: edge → origin shield → origin; offload calculation
- Cache keys: normalization, Vary header risks, pricing-tier grouping
- TTL/invalidation: all Cache-Control directives, surrogate keys, stale-while-revalidate
- Video streaming CDN: HLS/DASH TTLs, Netflix Open Connect
- Edge compute: Cloudflare Workers vs Lambda@Edge (latency comparison)
- Multi-CDN: DNS failover vs proxy routing, RUM-based steering
- Security: DDoS mitigation, WAF, cache poisoning, Keyless SSL
- HTTP/3 (QUIC): head-of-line blocking fix, 0-RTT, connection migration
- Design from scratch: PoP + shield + Kafka invalidation + DNS steering
- Capacity planning: origin offload math, storage sizing, cost modeling
- Failure runbooks: PoP outage, stale content, hit ratio drops
- Production config examples: Nginx, Cloudflare Workers, CloudFront signed URLs
- CDN for UGC, gaming, mobile, SaaS
- Core Web Vitals impact (LCP, TTFB)
- CI/CD testing for CDN configuration
- 5-level progression (Intern → Staff)

**Brainstorming questions covered:** 10 deep Q&A pairs
**War stories:** 5 (Fastly 2021, GitHub/Fastly, Stack Overflow, Pinterest, NPM)
**Reference numbers table:** 24 metrics with exact values
**Code examples:** 6 (Nginx config, Cloudflare Worker, CloudFront signed URL, Kafka invalidation, Varnish VCL, CI/CD testing)

---

## Part 57: Must-Know CDN Patterns — Quick Recall

Before walking into any system design interview, cement these five patterns:

**Pattern 1: Immutable versioned assets**
All JS, CSS, and image bundles get a content hash in the filename (`app.a1b2c3d4.js`). Set `Cache-Control: public, max-age=31536000, immutable`. CDN caches forever; browser caches forever. When the code changes, a new filename is generated — old caches are never stale, new code is always fetched. Zero invalidation required.

**Pattern 2: Short TTL + background revalidation for semi-dynamic content**
Product pages, category pages, blog posts. Set `Cache-Control: public, s-maxage=300, stale-while-revalidate=60, stale-if-error=3600`. CDN serves fresh for 5 minutes. After expiry, serves stale immediately while refreshing in background (user sees no delay). If origin is down, serves stale for up to 1 hour. Combines fast response with reasonable freshness.

**Pattern 3: Surrogate keys for any content with entity relationships**
Any page that displays data from a database entity (product, article, user profile) should include a `Surrogate-Key` header. When the entity updates, a single purge call by entity key invalidates all pages containing that entity. Scales to millions of pages; no manual URL tracking required.

**Pattern 4: Never cache authenticated responses**
Add a CDN rule: if request header `Authorization` is present OR cookie matching session patterns is present → bypass cache, set `Cache-Control: private, no-store` on response. This rule fires even if the application code forgets to set the right headers. Defense-in-depth.

**Pattern 5: Edge function for lightweight gate-keeping**
Auth token validation, rate limiting, and geographic routing belong at the CDN edge — not at origin. This stops unauthorized requests from reaching origin (cost savings, DDoS protection). Keep edge functions under 10ms CPU time. Anything heavier (database lookups, complex business logic) belongs at origin.

---

## Part 58: Common Patterns to Avoid

**Anti-pattern 1: Caching API responses without surrogate keys**
You cache `/api/products/page/1` for 5 minutes. A product price changes. The cached page shows the wrong price for up to 5 minutes. Fix: either use surrogate keys for instant invalidation, or accept shorter TTL (30s–60s) with stale-while-revalidate.

**Anti-pattern 2: Using query parameters for cache variants**
`/product/123?currency=USD` and `/product/123?currency=EUR` create separate cache entries. But users can generate arbitrary `?currency=FAKE` values that pollute the cache index with entries never requested again. Fix: normalize to a finite set of dimensions in a header, not query params. Strip unknown query params at the CDN edge.

**Anti-pattern 3: Long TTLs with no invalidation plan**
Setting `max-age=86400` (1 day) with no surrogate key support. When you need to update content urgently, you can only do URL-based purges — but you must know every URL that displays this content. For large sites this is impossible. Always add surrogate keys before setting TTL > 10 minutes.

**Anti-pattern 4: CDN as the only layer of authentication**
Relying on CDN Workers to validate JWTs and treating origin as implicitly trusted. If a CDN config change accidentally disables the Worker, origin becomes publicly accessible. Origin should always validate credentials independently (defense-in-depth). CDN auth at the edge is an optimization (fail fast, reduce origin load), not the security boundary.

**Anti-pattern 5: No CDN bypass for incidents**
CDN sits in front of all traffic with no DNS bypass plan. When CDN has an incident, you have no way to serve traffic directly from origin. Pre-plan: maintain a low-TTL DNS record pointing to origin, documented runbook for CDN bypass, origin capacity headroom for full traffic load.

---

## Part 59: Pre-Interview Drill — 12 Questions (Extended)

Answer each in 2 minutes or less before your interview:

1. A user in Singapore requests your US-hosted website. Walk through every network hop before the HTML bytes start flowing to their browser.
2. Explain the difference between `Cache-Control: no-cache` and `Cache-Control: no-store`. Which one still allows CDN caching?
3. Your product catalog page has a CDN hit ratio of 40% despite setting `s-maxage=3600`. Name four possible causes.
4. You need to purge all CDN cache for product ID 456, which appears on 50,000 pages across your site. How do you do it in under 30 seconds without knowing all 50,000 URLs?
5. Your CDN is using `Vary: Accept-Language`. You have 12 supported languages. Estimate the cache storage impact on a site with 1M unique URLs.
6. Compare `stale-while-revalidate` and `stale-if-error`. When would you use each?
7. Why is a Cloudflare Worker better than AWS Lambda@Edge for low-latency A/B testing?
8. Explain multi-CDN proxy routing vs DNS failover. Which is faster? What are the operational downsides of each?
9. An attacker is flooding your site with `GET /api/products?id=<random_guid>` at 100K RPS. Each request is a cache miss, hitting origin. How does your CDN help, and what additional mitigations do you add?
10. Your company is on CloudFront. A critical security bug was fixed and deployed 10 minutes ago. Some users are still seeing the old vulnerable JavaScript bundle. Why, and how do you fix it immediately?
11. Design the cache TTL strategy for these four assets: (a) homepage HTML, (b) React app bundle, (c) product JSON API response, (d) user dashboard HTML.
12. What is cache poisoning via the `Host` header? Give a concrete example of how an attacker exploits it and how you prevent it.

---

## Part 60: Final Checklist Before Leaving This Chapter

- [ ] Can draw the two-tier CDN architecture from memory (edge → shield → origin) with latency labels
- [ ] Can recite the 5 most important `Cache-Control` directives and what each does
- [ ] Know surrogates key / cache tag pattern and can implement it for a new product
- [ ] Know the difference between Cloudflare Workers (< 1ms) and Lambda@Edge (100-500ms cold start)
- [ ] Can explain origin offload math (95% hit rate → origin sees 5% of QPS)
- [ ] Know multi-CDN options (DNS failover 60s vs proxy routing <1s) and their trade-offs
- [ ] Know 3 cache poisoning attack vectors and their mitigations
- [ ] Can design a Kafka-based async CDN invalidation pipeline in 5 minutes
- [ ] Know CDN cost: CloudFront $0.0085/GB vs EC2 $0.09/GB (10× difference)
- [ ] Know the Fastly 2021 outage root cause (single BGP route advertisement failure)
- [ ] Can explain QUIC/HTTP3 benefits at CDN edge (no TCP HOL blocking, 0-RTT, connection migration)
- [ ] Have memorized: HIT = 1-5ms, MISS+origin = 50-200ms, tag purge = 5-30s, DNS failover = 60s

---

## Part 61: Why This Matters for Google L5 Interviews

CDN architecture appears in Google L5 interviews in multiple forms:

**Direct CDN question:** "Design a CDN" or "Explain how Cloudflare works." Less common at L5 (more common at L6/Staff), but entirely possible if the panel includes someone from Google's networking or infra team.

**System design integration:** CDN knowledge is expected as background when designing any globally-serving system. "Where would you add caching?" — at L5, the interviewer expects you to mention CDN for static assets without prompting. If you don't bring it up, they may ask explicitly, and your answer determines whether you're demonstrating awareness of the full production stack.

**Estimation questions:** "How many requests per second can your origin handle?" — knowing CDN offloads 95% of traffic lets you size the origin at 5% of total load, which is a significant influence on the capacity estimate.

**Failure mode awareness:** "What happens if your cache layer fails?" — a strong L5 answer covers CDN origin bypass, stale serving via `stale-if-error`, and failover to secondary CDN. This shows operational maturity beyond textbook design.

**Specific to Google:** Google runs its own CDN infrastructure (Google Cloud CDN, built on GFE — Google Front End). Understanding CDN architecture helps you speak the language of Google's infra team. Google's GFE is an anycast global load balancer + CDN layer in front of all Google services — conceptually identical to what this chapter covers.

One-line pitch for the interview: *"I'd put a CDN in front of all public-read traffic. Static assets get 1-year TTL via versioned URLs. Semi-dynamic content gets 5-minute TTL with surrogate key purging for instant invalidation on updates. Authenticated APIs bypass the cache entirely. This gives us 95%+ origin offload and sub-5ms response time for the majority of user requests."*

---

## Part 62: Additional Quick-Reference Diagrams

**Cache header decision tree for an origin server engineer:**

```
Is this response user-specific?
   YES → Cache-Control: private, no-store

Is this response sensitive (auth, payment, permissions)?
   YES → Cache-Control: no-store

Does this response change more often than once per hour?
   YES → Cache-Control: public, s-maxage=60, stale-while-revalidate=30
   NO  → Cache-Control: public, s-maxage=3600, stale-while-revalidate=60

Is this asset versioned (hash in filename)?
   YES → Cache-Control: public, max-age=31536000, immutable
```

**Surrogate key naming conventions used at scale:**

```
Entity type        Key pattern            Example
Product            product-{id}           product-789
Category           category-{slug}        category-shoes
Article            article-{id}           article-4521
Author             author-{id}            author-99
Homepage           homepage               homepage
Search results     search                 search (broad purge)
User profile       user-{id}              user-1234 (private, not CDN-cached)
```

**CDN selection quick guide:**

```
Need maximum security + DDoS → Cloudflare
Need most programmatic control (VCL) → Fastly
Already on AWS + want simplicity → CloudFront
Need 99.999% SLA + enterprise support → Akamai
Budget: flat-fee, high volume → Cloudflare
Budget: pay-as-you-go, unpredictable volume → CloudFront or Fastly
Edge compute, low latency (< 5ms) → Cloudflare Workers
Edge compute, Node.js/Python support → Lambda@Edge
```

---

## Part 63: Ten Things About CDNs That Surprise Engineers

1. **CDN egress is 10× cheaper than EC2 egress.** Most engineers assume CDN adds cost. At any meaningful scale, CDN reduces total cost by absorbing egress and reducing origin compute.
2. **Cloudflare Workers cold start is under 1ms** because they use V8 isolates, not containers. A container-based function (Lambda) pays 100–500ms per cold start; a Worker pays essentially nothing.
3. **`no-cache` still allows caching** — it just requires revalidation on every use. `no-store` actually prevents caching.
4. **CDN PoPs don't share cache** — a user in Chicago and a user in Dallas might both miss the cache independently because they hit different PoPs. This is expected and why overall CDN hit ratio is never 100%.
5. **The origin shield is a second cache layer, not a proxy.** Its entire purpose is to aggregate cache misses from many edge PoPs into a single cache entry so origin sees far fewer unique requests.
6. **HTTP/2 push was removed from Chrome** in 2022 because it rarely helped in practice. The replacement is `103 Early Hints`, which gives browsers a head start without the complexity of server push.
7. **Fastly 2021 was caused by one customer's config change** — Fastly had a software bug triggered by a specific configuration value, and a customer accidentally triggered it. The CDN's own configuration handling caused the outage, not a DDoS or infrastructure failure.
8. **Signed URLs expire**, so CDN cannot cache them long-term. Use `s-maxage` shorter than the signature TTL, or use Signed Cookies instead (no URL change needed — all requests from a browser carry the cookie).
9. **`Vary: Accept-Encoding` creates at most 2–3 variants** (gzip, br, identity). This is safe. `Vary: User-Agent` would create thousands of variants. Never use `Vary: User-Agent` on a CDN-fronted response.
10. **Multi-CDN costs more than single CDN** — you pay egress to both CDNs, plus configuration management overhead. The benefit is resilience. Evaluate whether your SLA requires it before adding the complexity.

---

## Part 64: CDN Chapter — Final Summary Table

| Topic                    | Key Point                                                              | Number to Remember              |
|--------------------------|------------------------------------------------------------------------|---------------------------------|
| Why CDN                  | Speed of light limit; copy data close to user                          | ~200 km/ms propagation delay    |
| PoP architecture         | Anycast BGP routes to nearest PoP                                      | 450+ PoPs (Cloudflare)          |
| Two-tier caching         | Edge + shield + origin hierarchy                                        | Origin sees 3% of traffic       |
| Cache HIT                | Served from edge PoP memory                                            | 1–5 ms latency                  |
| Cache MISS               | Edge → shield → origin round trip                                       | 50–200 ms total                 |
| Max-age                  | Client + CDN cache duration                                            | 1 year for versioned assets     |
| S-maxage                 | CDN-only cache duration (overrides max-age)                            | 300s for semi-dynamic           |
| Stale-while-revalidate   | Serve old, refresh in background                                       | No user-visible wait            |
| Surrogate keys           | Purge by entity, not URL                                               | 5–30s propagation               |
| Vary: Cookie             | Never for public content (fragmentation)                               | N variants × M URLs = explosion |
| Cloudflare Workers       | Edge compute, V8 isolates                                              | < 1ms cold start                |
| Lambda@Edge              | Edge compute, container-based                                          | 100–500ms cold start            |
| CDN egress cost          | CDN is cheaper than origin egress                                      | $0.0085 vs $0.09/GB (10×)       |
| DNS failover             | Switch to origin or backup CDN via DNS                                 | 60 seconds (DNS TTL bound)      |
| Fastly 2021 outage       | Single BGP route advertisement failure → global CDN outage             | 50% of internet affected        |
| HTTP/3 (QUIC)            | No TCP HOL blocking, 0-RTT, connection migration                       | 20–40% faster on lossy networks |
| Cache poisoning          | Host header injection, request smuggling, web cache deception          | Validate Host header always     |
| Origin shield            | Second-tier cache; aggregates edge PoP misses                          | 2–4× additional origin offload  |
| Request coalescing       | Collapse N simultaneous misses into 1 origin request                   | Thundering herd prevention      |
| Web cache deception      | Attacker tricks CDN into caching private pages via extension spoofing  | Cache based on headers, not URL |
| Core Web Vitals          | CDN directly improves LCP and TTFB for Google ranking                  | HIT = sub-5ms TTFB              |
| Break-even (Cloudflare)  | Flat fee wins vs CloudFront above ~24 TB/month                         | $200/month vs ~$1.7K/month      |
| Multi-CDN                | DNS failover (60s) vs proxy routing (instant)                          | RUM drives routing decisions    |
| Cache warming            | Proactively populate CDN on deploy or entity update                    | Prevents cold miss storms       |
| 0-RTT (QUIC)             | Client sends HTTP request in same packet as TLS handshake              | Saves 1 RTT on reconnect        |

---

## End Notes

The CDN is the first layer of every production system that serves content at scale. Mastering CDN architecture means understanding two deeply connected systems: how content flows efficiently from servers to users (caching, routing, compression), and how that efficiency is maintained safely (invalidation, security, monitoring). These two concerns are in permanent tension — efficiency wants long TTLs; safety wants short TTLs. Surrogate keys resolve that tension. That resolution is the core insight of this chapter.

At Google scale, every millisecond of CDN hit latency improvement represents millions of user-hours saved daily. At interview scale, demonstrating that you understand the quantitative tradeoffs — origin offload math, cost per GB, hit ratio by content type, cold start latency — is what separates a candidate who has used a CDN from one who can design with one.

Read this chapter again two days before the interview. The numbers in the quick-reference table (Part 38) and the five key patterns (Part 57) are the highest-return items to commit to memory. Everything else provides the depth to answer follow-up questions confidently.

---

## Chapter Statistics

- **Parts covered:** 64
- **Total lines:** ~2,000
- **Code examples:** 7 (Nginx, Varnish VCL, Cloudflare Worker, CloudFront signed URL, Kafka invalidation service, CI/CD cache header testing, Edge A/B routing)
- **War stories:** 5 (Fastly 2021, GitHub/Fastly 2020, Stack Overflow CDN drift 2018, Pinterest hot partition 2014, NPM thundering herd 2018)
- **Reference numbers:** 24 metrics with exact values (Part 38, Part 47)
- **Brainstorming Q&A pairs:** 10 deep questions
- **Interview drills:** 12 + 12 extended (Parts 18, 59)
- **Exercises:** 10 (Parts 20, 40)
- **Homework assignments:** 8 (Parts 21, 54)
- **Content freshness:** Covers HTTP/3, 0-RTT, QUIC, Cloudflare Workers, 103 Early Hints — all current as of 2024–2025
- **Level targeting:** Section 6 Staff/L6 format — suitable for Google L5 interview prep with 5-level progression included
- **Unique value:** Covers cache key fragmentation (pricing-tier grouping), request coalescing mathematics, multi-CDN operational trade-offs, and CDN security failure modes not covered in typical system design resources
- **Covers for interviews at:** Google, Meta, Amazon, Stripe, Cloudflare, Netflix, and any company where a Staff engineer would design high-traffic content serving infrastructure
- **Study order within chapter:** Start with Parts 1–7 (fundamentals + two-tier hierarchy + cache keys + TTL), then Parts 22–27 (quantitative + HTTP/3 + design from scratch), then Parts 38–40 (quick reference + checklist + exercises). Deep-dive parts (security, gaming, mobile) are enrichment.
- **Suggested total study time:** First pass 90 minutes (read all parts). Review pass 30 minutes (Parts 38, 57, 64). Pre-interview drill 10 minutes (answer Part 59 questions aloud).
- **Cross-references:** Chapter 100 (Video Streaming), Chapter 55 (Search System), Chapter 93 (Advanced Topics: thundering herd, cache invalidation patterns), Chapter 10 (APIs: HTTP caching headers in the API context), Chapter 98 (Spanner: global serving architecture that CDNs complement).
- **Summary:** A CDN turns a physics problem (latency from distance) into an engineering problem (cache management). Solve the cache management problem well and your users get fast responses regardless of geography.
- **Key insight to internalize:** The CDN is not a single cache — it is a hierarchy of caches (edge + shield + browser), each adding a layer of latency reduction and origin protection. Understanding all three layers and how they interact is what this chapter is for.
- **Final thought:** Every 100ms of latency reduction increases conversion rates by ~1% (Amazon's classic data). CDN is not infrastructure overhead — it is a revenue-generating investment.

---

*Pairs with Chapter 100 (Video Streaming) for CDN usage in video delivery, Chapter 55 (Search System) for CDN-cached search result pages, and Chapter 93 (Bonus Advanced Topics) for cache invalidation patterns.*

`Chapter 107 | Section 6: Staff/L6 Systems | CDN Architecture`

---

## Interview Simulation — CDN Architecture (Staff / L6)

*45-minute Staff-level system design interview. Phases follow the Section 2 framework.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a CDN from scratch. Where do you start?

**Candidate:** Before I draw a single box, let me ask some clarifying questions. First — are we designing a general-purpose CDN (like Cloudflare or Akamai) or a CDN optimized for a specific workload, like video streaming or API responses? The cache strategy differs significantly. Second — what's the target global latency SLA — < 20 ms to 95% of users, < 50 ms to 99%? Third — do we need to support dynamic content (which can't be cached) in addition to static assets? Fourth — cache invalidation: do we need near-instant purge (< 1 s globally) or is eventual invalidation (1–5 min) acceptable?

> **Interviewer:** General-purpose CDN. < 50 ms p99 latency globally. Support both static and dynamic content. Cache invalidation must propagate to all PoPs within 30 seconds for static, pass-through for dynamic.

**Candidate:** Functional requirements: (1) Cache and serve static assets (images, JS, CSS, video segments) from the nearest PoP. (2) Pass dynamic requests through to origin with connection reuse optimization. (3) Propagate cache invalidations to all PoPs within 30 s. (4) Provide origin shield to reduce origin load. Non-functional: < 50 ms p99 globally, 99.99% availability, support 10 Tbps peak egress bandwidth, anycast routing to direct users to nearest PoP automatically.

---

### Phase 2: Estimation (4 min)

**Candidate:** 10 Tbps peak egress. At 1 Mbps average bitrate per user connection, that's 10 million concurrent users. To achieve < 50 ms globally, we need PoPs within 3,000 km of every significant user population — that's roughly 50 PoPs covering NA, EU, APAC, LATAM, MEA. Each PoP handles 10 Tbps / 50 = 200 Gbps average. A 200 Gbps PoP requires roughly 50 servers at 10 Gbps NIC each (with bonding). Cache storage: 10 Tbps egress, assume average object is 100 KB, 70% cache hit rate → 3 Tbps served from cache. Cache working set: if the hot 20% of objects serve 80% of requests (Zipf), and we can hold 10 TB per PoP → we cover the top ~100 million objects per PoP. Object metadata index: 100M objects × 128 bytes per metadata record = 12.8 GB in RAM per PoP — fits in a single server with 64 GB RAM.

---

### Phase 3: API Design (4 min)

**Candidate:** Three APIs. Cache purge: `POST /v1/purge` body `{urls: [...], surrogate_keys: [...]}` — URL-level and surrogate key purge. Returns `{purge_id, estimated_propagation_ms}`. Cache status: `GET /v1/cache/status?url=...` returns hit/miss state at each PoP region. Origin configuration: `PUT /v1/origins/{hostname}` body `{shield_region, cache_rules: [{path_pattern, ttl, cache_control_override}], dynamic_rules: [{path_pattern, bypass_cache: true}]}`. The cache_rules allow the customer to override Cache-Control headers from origin — critical when origins return `Cache-Control: no-cache` on assets that are actually static. Content negotiation: the CDN must respect `Vary` headers — if origin returns `Vary: Accept-Encoding`, the CDN caches separate copies for gzip and brotli.

---

### Phase 4: Data Model (4 min)

**Candidate:** Two layers of metadata. In-memory at each PoP (LRU hash map): `{cache_key → {stored_at, ttl, size_bytes, storage_location, headers_blob}}`. Cache key is typically SHA256 of (hostname + path + normalized query string). This is the hot path for every cache lookup — must be sub-millisecond. On-disk at each PoP (RocksDB): the actual object bytes, keyed by the same SHA256. We use a log-structured merge tree (RocksDB) because it optimizes for write throughput (new cached objects) while supporting fast point lookups for cache hits. For invalidation, we maintain a `purge_log` table in a globally consistent store (CockroachDB or Spanner): `{purge_id, url_pattern, surrogate_key, issued_at, propagated_to_regions}`. Each PoP subscribes to this log and applies purges.

---

### Phase 5: HLD + Deep Dive (20 min)

```
CDN ARCHITECTURE
=================

USER REQUEST (anycast routing)
  │
  │  DNS: user's resolver queries for cdn.example.com
  │  Anycast IP: all PoPs announce the same IP via BGP
  │  IP routing: user's packet routed to topologically nearest PoP
  │
  ▼
EDGE PoP (50 locations globally)
  │
  ├─ Cache Lookup (in-memory LRU, < 1ms)
  │   │
  │   ├─ HIT (70-99% for static assets):
  │   │   serve from RocksDB on-disk cache
  │   │   update LRU metadata
  │   │   return to user with cache headers (X-Cache: HIT)
  │   │
  │   └─ MISS: forward to Origin Shield
  │
  ▼
ORIGIN SHIELD (1-3 regional mid-tier nodes per continent)
  │  request coalescing: collapse 1000 simultaneous misses
  │  for same object into ONE upstream request
  │
  ├─ HIT (shield cache): return to edge, edge caches it
  │
  └─ MISS: fetch from Customer Origin
  │
  ▼
CUSTOMER ORIGIN (customer's web server / S3 / etc.)
  │  single connection reuse (HTTP/2 multiplexing)
  │  response cached at shield, then at edge
  │
  ▼  (reverse path, object cached at each layer)
  └─► Edge PoP → User

CACHE INVALIDATION PROPAGATION
================================
Customer calls POST /v1/purge
  │
  ▼
Purge Coordinator (global, Spanner-backed)
  │ writes purge record: {purge_id, pattern, timestamp}
  │
  ▼
Pub/Sub Fan-out (Google Cloud Pub/Sub, per-region topics)
  │ one message per PoP region
  │
  ▼
PoP Purge Worker (running at each PoP)
  │ receives purge message, matches in-memory index
  │ marks matching objects as STALE (zero TTL)
  │ acknowledges back to Purge Coordinator
  │
  ▼
Purge Coordinator tracks propagation
  │ SLA: all PoPs acknowledge within 30s
  │ if any PoP misses ack in 25s → retry
  └─► Customer can query /v1/cache/status for confirmation
```

**Deep Dive 1: Anycast Routing and PoP Placement.**

Anycast is the foundation of CDN low-latency routing. We announce the same IP address block (e.g., 203.0.113.0/24) from all PoP locations via BGP. When a user anywhere in the world sends a packet to that IP, the internet's routing protocols forward it to the topologically nearest PoP that announces that prefix. No DNS-based geographic routing needed — the network itself does the routing. The placement constraint: a PoP must be in an IXP (Internet Exchange Point) or colocation facility with good peering to the local ISPs. Akamai and Cloudflare have PoPs in 300+ IXPs globally — that's the moat. For a new CDN, the minimum viable global coverage is: Ashburn VA (covers US East), Los Angeles (US West), Frankfurt (EU), Singapore (APAC), São Paulo (LATAM), Johannesburg (MEA). Six PoPs get you < 100 ms to 80% of global internet users. Fifty PoPs get you < 50 ms to 95%.

> **Interviewer:** How does origin shield protect the origin during a cache miss storm?

**Candidate:** *(Cross-question: thundering herd at origin shield)* Request coalescing is the key mechanism. When 10,000 edge nodes simultaneously miss on a popular new object, without a shield each would send an independent request to origin — 10,000 simultaneous origin requests, likely overwhelming it. The shield is a regional proxy layer (1 per continent). All 10,000 edge misses route to the nearest shield node. The shield checks its own cache: if already cached, it serves all 10,000 requests without touching origin. If not cached, it holds all 10,000 requests in a queue and sends exactly ONE request to origin. When origin responds, the shield caches the object and fans out the response to all 10,000 waiting edge nodes simultaneously. The implementation detail: the shield uses a "request deduplication map" — a hash map of in-flight requests keyed by cache_key. Subsequent requests for the same key join the wait queue rather than triggering a new origin fetch.

**Deep Dive 2: Cache Invalidation Propagation.**

The 30-second SLA for full propagation requires a reliable fan-out with delivery guarantees. Our design uses Pub/Sub per region (50 topics for 50 PoPs). The Purge Coordinator writes the purge record to Spanner (durable) then publishes to all 50 topics. Each PoP's Purge Worker subscribes to its regional topic, receives the message, and applies the purge locally. The worker acknowledges to the Purge Coordinator (via a write to a `purge_acks` table in Spanner). The Coordinator has a 25-second SLA monitoring job: if any PoP hasn't acknowledged by 25 s, it re-publishes the purge message to that PoP's topic. The reason for 25 s (not 30 s) is to leave a 5-second retry window. Failure mode: a PoP is partitioned from Pub/Sub. In this case, the PoP continues to serve stale content until it reconnects and processes the queued purge. We expose this state to the customer via the `/v1/cache/status` API — "PoP us-east-1: PENDING purge." For emergency purges (security incidents), we support a hard TTL override: the Purge Worker sets the in-memory TTL to -1, forcing every subsequent request to re-validate with origin until the purge propagates.

**Deep Dive 3: Cache-Control Strategy for Different Content Types.**

This is where most teams get it wrong at scale. Static versioned assets (JS/CSS with content hash in filename, `main.a3f7b2.js`): `Cache-Control: public, max-age=31536000, immutable`. One year TTL, `immutable` tells the browser never to revalidate. Changing the content means changing the filename — no CDN invalidation ever needed. This is the ideal case. HTML pages: `Cache-Control: public, max-age=60, stale-while-revalidate=3600`. 60-second TTL ensures freshness for most users; `stale-while-revalidate` means the CDN can serve stale content for up to an hour while asynchronously fetching a fresh copy — eliminates the latency spike on cache expiry. Dynamic API responses: `Cache-Control: no-store`. CDN passes through to origin. But we still benefit from connection reuse and protocol optimization (HTTP/2 over TCP vs HTTP/1.1 from user to CDN edge). User-specific content: never cache on the CDN without a `Vary: Cookie` or `Vary: Authorization` header, and even then, each user's cached copy is separate — the cache hit rate is near zero, so CDN is just a transport optimization here, not a cache.

---

### Common Cross-Questions and Strong Answers (Staff Level)

**Q: How do you handle a large file (10 GB video) that nobody has requested yet — the first user gets slow download while the CDN fetches from origin?**
A: Range request support and segmented caching. The CDN fetches the file from origin in 1 MB chunks as the user requests bytes. The first user pays the origin latency for each chunk; subsequent users for the same chunk get it from cache. For predictive prefetch: if we know a video is about to be released (a scheduled content release), we push-prefetch the first 3 MB of each segment to all PoPs 5 minutes before go-live. For large live event content (Super Bowl), we proactively warm all edge caches before the event using a CDN-internal prefetch API.

**Q: A customer reports that their cache purge worked in NA but not in APAC 45 seconds later. How do you debug this?**
A: Check the `purge_acks` table in Spanner: is there an acknowledgment from the APAC PoPs? If no ack from ap-southeast-1, the Pub/Sub message was not received or the Purge Worker failed to process it. Check Purge Worker logs at the APAC PoP: did it receive the message? Did the pattern match fail (URL encoding mismatch between the purge request and the cached URL)? URL normalization bugs are the most common cause — the cache key stored `%20` but the purge request used spaces. Our canonical cache key generation normalizes URLs before storage and before matching, but encoding inconsistencies in customer-supplied URLs slip through. Fix: add a URL normalization step in the Purge Coordinator before writing the purge record.

**Q: How do you handle TLS certificate management across 50 PoPs for thousands of customer domains?**
A: We use a centralized certificate store (HashiCorp Vault or AWS ACM Private CA) for our own wildcard certificate (`*.cdn-provider.com`). For customer custom domains (CNAME to our CDN), we provision certificates via ACME (Let's Encrypt or ZeroSSL) per domain, stored in the certificate store and pushed to all PoPs via a certificate distribution service. Certificate push is triggered on new domain creation and 30 days before expiry. The PoP's TLS terminator (Nginx or Envoy) hot-reloads certificates without dropping connections. At 50,000 customer domains × 50 PoPs, the certificate store holds 2.5 million certificate objects — manageable with a well-indexed KV store. The operational risk is certificate expiry: our monitoring alerts at 45 days remaining, and the renewal job runs at 30 days remaining with a 3-retry policy.

---

*Pairs with Chapter 100 (Video Streaming) for CDN usage in video delivery, Chapter 55 (Search System) for CDN-cached search result pages, and Chapter 93 (Bonus Advanced Topics) for cache invalidation patterns.*

`Chapter 107 | Section 6: Staff/L6 Systems | CDN Architecture`
