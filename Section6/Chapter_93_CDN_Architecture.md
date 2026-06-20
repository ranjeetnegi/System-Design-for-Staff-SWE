# Chapter 96: CDN Architecture — How a CDN Actually Works

> CDN appears as a tool in almost every system design answer. But "put it behind
> a CDN" is L4 thinking. L6 knows how a CDN works internally: PoP placement,
> anycast routing, cache hierarchies, origin shield, and what happens on a cache miss
> at 10 million requests per second.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

CDN is referenced throughout the guide (Ch31, Ch56, Ch62, Ch89) but never explained
as a system in itself. Rare but deep interview question at companies that build
or operate CDNs (Cloudflare, Fastly, Akamai, AWS CloudFront team) and comes up
as a follow-up at any company: "You said use a CDN — how does the CDN actually
serve the request?"

---

## Planned Content

### Part 1: The Problem CDNs Solve
- Speed of light: London → Sydney = 85ms minimum; a CDN PoP in Sydney = 5ms
- Origin overload: 1M requests/second to one origin server is impossible
- CDN moves content physically closer to users and absorbs load from origin
- Content types: static (images, JS, CSS, video) vs. dynamic (API responses, personalized)

### Part 2: Points of Presence (PoPs)
- PoP: a datacenter at an internet exchange point (IXP), peering with ISPs
- Cloudflare: 300+ PoPs; Akamai: 4,000+ PoPs; AWS CloudFront: 400+ PoPs
- Placement strategy: major cities, major IXPs (Equinix, DE-CIX, LINX)
- Each PoP: hundreds of servers, multiple ISP peering connections, SSD cache
- Tier 1 PoPs (large, many connections) vs. Tier 2 PoPs (smaller, forward misses to Tier 1)

### Part 3: Anycast Routing — How Requests Reach the Right PoP
- Unicast: one IP = one server location
- Anycast: same IP announced from 300 locations; BGP routes user to nearest PoP
- How it works: Cloudflare announces 104.16.0.0/12 from every PoP globally
  → your ISP's BGP routing sends you to the closest PoP automatically
- Failover: if a PoP goes down, BGP withdraws its announcement; traffic shifts to
  next-closest PoP within seconds (BGP convergence time: 30–60s)
- DNS-based routing (alternative): Akamai uses GeoDNS — resolve CDN hostname to
  nearest PoP's IP. Slower to failover (DNS TTL), but more controllable.

### Part 4: Cache Hierarchy
- Edge cache (PoP): serves most requests; LRU eviction; SSD storage
- Regional cache (mid-tier / origin shield): aggregates misses from multiple edge PoPs
  before hitting origin; reduces origin load by 10-100x
- Origin: the customer's actual servers; only sees cache misses
- Cache key: URL + selected headers (Vary: Accept-Encoding, Accept-Language)
- ASCII diagram: User → Edge PoP → Regional PoP → Origin Shield → Origin

### Part 5: Cache Miss Handling — The Request Collapse Problem
- Thundering herd: 10,000 users request the same uncached object simultaneously
  → 10,000 requests hit origin in parallel → origin overload
- Request coalescing (collapse): PoP receives 10,000 requests for same object,
  sends ONE request to origin, holds the other 9,999, responds to all when object arrives
- Cache lock: first request acquires a lock on the cache key; others wait
- Stale-while-revalidate: serve stale content immediately, refresh in background
  → no thundering herd, slight staleness

### Part 6: Cache Invalidation
- TTL-based: cache expires after N seconds (simple, eventual consistency)
- Purge API: customer calls CDN API to invalidate specific URLs immediately
  → Cloudflare purge propagates to all PoPs in ~150ms
- Surrogate keys (cache tags): tag cached objects with keys (e.g., "product:12345")
  → purge all objects tagged "product:12345" in one API call
- Versioned URLs: embed version in URL (style.v3.css) → old URL stays cached,
  new version is a cache miss (most reliable, no purge needed)

### Part 7: Dynamic Content and Edge Computing
- Dynamic content: personalized pages, API responses — traditionally not cached
- Edge caching for APIs: cache with Vary headers on user segment, not individual user
- Edge computing (Cloudflare Workers, Lambda@Edge): run code at the PoP
  → A/B testing at edge, auth at edge, request transformation at edge
  → reduces round trips to origin for logic that doesn't need origin data
- Streaming: video segments are cacheable; live streams are not (or very short TTL)

### Part 8: SSL/TLS Termination at Edge
- TLS handshake: adds 1-2 round trips (100-300ms for distant users)
- CDN terminates TLS at the nearest PoP → TLS handshake is 5ms not 85ms
- Backend connection: PoP → origin can be HTTP or HTTPS (internal network, less latency)
- Certificate management: CDN manages certificates for customer domains (Let's Encrypt or custom)

### Part 9: Interview Framework
- When asked "how does a CDN work": anycast → nearest PoP → cache hit or miss
  → cache hierarchy → origin on miss → request coalescing
- When asked about cache invalidation: TTL + purge API + versioned URLs (three strategies)
- When asked about dynamic content: Vary headers + edge computing
- L5 vs. L6: L5 says "CDN caches static content near users"; L6 explains anycast routing,
  request coalescing, origin shield, and why versioned URLs are more reliable than purge APIs

---

## The One-Sentence Summary

> "A CDN works by announcing the same IP from 300+ global PoPs via anycast BGP (user automatically routes to nearest), serving requests from a multi-tier cache hierarchy (edge → regional → origin shield → origin), and using request coalescing to prevent thundering herd on cache misses — 'put it behind a CDN' is the answer; explaining the anycast + coalescing mechanics is what L6 adds."

---

*Full chapter: ~2,500 lines. Pairs with Ch31 (Caching at Scale) and Ch89 (Video Streaming).*
