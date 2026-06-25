# Chapter 61b: Web Crawler — Indexing the Internet

> A web crawler sounds simple: follow links, download pages. At Google scale,
> you are fetching 20 billion pages, respecting 500 million robots.txt files,
> and deduplicating a petabyte of content — all without hammering any single
> website into the ground.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Web Crawler                                |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify (breadth vs. focused, scale, freshness)     |
|  Min 2-9:   Users & use cases                                    |
|  Min 9-16:  Functional requirements                              |
|  Min 16-21: Scale math                                           |
|  Min 21-26: Non-functional requirements                          |
|  Min 26-29: Assumptions                                          |
|  Min 29-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                            |
|                                                                  |
|  Key numbers to know:                                            |
|  - Web: ~20B indexable pages, ~50B with crawl traps             |
|  - Average page: 100-500 KB raw HTML                             |
|  - Google crawls: ~1B pages per day                              |
|  - 1B pages/day = 11,600 pages/sec sustained                    |
|  - Freshness: news=hourly, e-commerce=daily, static=weekly      |
|  - Robots.txt: ~500M unique domains have one                     |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Single datacenter crawl                                       |
|  - 1B pages, fixed seed list                                     |
|  - URL frontier, Bloom filter dedup, politeness                  |
|  - Basic freshness (static schedule)                             |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Multi-datacenter, geo-aware crawling                         |
|  - 20B pages, dynamic prioritization via PageRank signal        |
|  - Cross-DC coordination, crawl budget allocation               |
|  - Adaptive freshness (ML-driven revisit scheduling)            |
|  - JS rendering pipeline at scale (Puppeteer fleet)             |
|  - International crawl: robots.txt in 50 languages              |
+------------------------------------------------------------------+
```

---

## Phase 1: Users and Use Cases (Minutes 2-9)

### Who uses a web crawler?

Think of a web crawler like a postal worker who visits every house in every city in the world, takes a photo of each house, and reports back to headquarters. The headquarters then organizes all those photos so people can search them.

**Human users (indirect — they never touch the crawler):**
- Search engine users: 5 billion Google searches per day depend on the crawler having visited pages recently
- Webmasters and SEO engineers: they need the crawler to find their new pages within 24-48 hours of publishing
- Content quality teams: they review what the crawler found, remove spam pages from the index

**System users (the crawler's direct consumers):**
- Search indexer: receives parsed page content from the crawler, builds the inverted index
- PageRank pipeline: receives the link graph extracted by the crawler to compute page authority scores
- Freshness monitor: tracks when the crawler last visited each page, triggers urgent re-crawls for news
- Spam detection pipeline: analyzes crawled content to detect link farms and low-quality pages
- Analytics dashboard: reports crawl coverage, success rates, and domain health to engineering

**Operational users:**
- SRE oncall: monitors crawl health, gets paged when fetch error rate spikes
- Domain-specific teams: can request priority crawls for newly acquired domains
- Policy/legal team: maintains a blocklist of domains not to crawl (legal, privacy, national restriction)

### Core use cases (P0 = must have, P1 = important)

**P0 — Must have:**
- UC1: Discover new pages from seed URLs and extract outbound links recursively
- UC2: Download page content (HTML, PDF, XML) and store it durably
- UC3: Respect robots.txt — never fetch pages a domain has forbidden
- UC4: Deduplicate URLs — never crawl the same URL twice (within a crawl cycle)
- UC5: Rate-limit per domain — no DDoS-ing any website

**P1 — Important:**
- UC6: Revisit pages on a schedule (freshness-based)
- UC7: Handle HTTP redirects (301, 302) correctly
- UC8: Report crawl health metrics per domain (success rate, latency, robots.txt compliance)

**Out of scope for L5:**
- Multi-datacenter crawling (L6)
- JavaScript rendering for SPA sites (mention as extension, don't design it)
- International robots.txt (multi-language)
- Crawl budget negotiation with webmasters

### Edge cases with architecture implications

- **Crawl traps**: Calendar pages, infinite query parameter combinations (/?page=1, /?page=2, ... /?page=999999). Without detection, the crawler fills its queue with garbage and never finishes. This forces a URL normalization layer and depth limit.
- **Duplicate content via different URLs**: `http://example.com/page` and `https://EXAMPLE.COM/Page?utm_source=google` are the same page. Forces content-level dedup (SimHash) in addition to URL dedup.
- **Large pages**: Some pages are 10 MB+ (entire Wikipedia dumps in one HTML file). Forces a page size cap in the fetcher.
- **Domain velocity abuse**: Some spam domains generate 10 million new URLs per second to exhaust crawler resources. Forces a per-domain URL cap.

### Alignment check (say this to the interviewer)

> "To confirm scope: I am designing a general-purpose breadth-first web crawler that discovers and stores 1 billion HTML pages from a fixed seed list, in a single datacenter. It respects robots.txt, deduplicates URLs using a Bloom filter, and enforces per-domain politeness. I am not designing the search indexer that consumes the content, and I am treating JavaScript-rendered pages as out of scope for now. Does this match what you want?"

---

## Phase 2: Functional Requirements (Minutes 9-16)

### Read flows

- **F1 — Fetch page**: Given a URL, download the page content over HTTP/HTTPS. Return the HTML body, status code, and response headers (including Content-Type, Last-Modified, ETag).
- **F2 — Read robots.txt**: For any new domain, fetch `domain.com/robots.txt` before crawling any page on that domain. Cache the result for 24 hours.
- **F3 — Read URL frontier**: A component (the scheduler) reads the next batch of URLs to crawl, respecting per-domain rate limits.

### Write flows

- **F4 — Enqueue discovered URLs**: After parsing a fetched page, extract all outbound links. Normalize each URL, check the dedup filter, and add new ones to the frontier queue.
- **F5 — Store raw content**: Save the full HTML of each successfully fetched page to content store, keyed by URL hash + timestamp.
- **F6 — Mark URL as visited**: After a successful fetch, update the visited-URL store so the URL is never fetched again in this cycle.
- **F7 — Update crawl metadata**: Record per-URL: last fetch time, HTTP status code, content hash, redirect chain, robots.txt ruling.

### Control flows (L5 signal — many candidates miss these)

- **F8 — Robots.txt enforcement**: Before any fetch, the fetcher must check: is this URL blocked by robots.txt for our user-agent? If blocked, mark the URL as "robots-blocked" and never attempt it.
- **F9 — Rate limit enforcement**: Before each fetch, check if the domain's token bucket has capacity. If not, delay the URL and try another domain. Per-domain: maximum 1 request/second.
- **F10 — Crawl depth limit**: Never follow links more than 10 hops from a seed URL. This prevents crawl traps.
- **F11 — Dead link pruning**: If a URL returns 404 or 410 three times in a row across crawl cycles, mark it as permanently dead and stop re-queuing it.
- **F12 — Revisit scheduling**: After a page is crawled, schedule its next revisit based on how frequently its content changes (news sites = hourly, e-commerce = daily, static docs = weekly).

### Key principle: specify WHAT, not HOW

These requirements define what the system must do, not how it does it. The URL frontier must respect politeness — that is a requirement. Whether it uses Kafka topics or Redis queues is a design decision made later.

---

## Phase 3: Scale and Capacity (Minutes 16-21)

### User scale

- Target: crawl 1 billion pages per crawl cycle
- Freshness window: average page revisited every 7 days
- Daily crawl volume: 1B pages / 7 days = ~143 million pages/day

### Activity scale (show the math)

```
Pages per day:  143M pages/day
Pages per sec:  143M / 86,400 sec = 1,655 pages/sec (sustained)
Peak factor:    3x for burst crawls when new content floods in
Peak:           ~5,000 pages/sec

Average page size: 200 KB (HTML) + 50 KB extracted links = 250 KB
Daily content:     143M * 250 KB = 35.75 TB per day
Annual content:    35.75 TB * 365 = 13 PB per year

URL store (Bloom filter):
  1B URLs * 10 bits per URL = 10 Gb = 1.25 GB RAM

Link graph edges:
  Average page has 30 outbound links
  1B pages * 30 = 30B edges (not stored in crawler, handed to PageRank)

robots.txt:
  500M unique domains
  Average robots.txt: 2 KB
  Total: 500M * 2 KB = 1 TB (cached in distributed store, 24hr TTL)
```

### Read/write ratio

- Reads (fetch pages): 1,655/sec sustained
- Writes (store content): 1,655/sec sustained (1:1 with reads)
- Writes (enqueue discovered URLs): 1,655 * 30 links = 49,650 URL enqueues/sec
- Reads (URL dedup check): 49,650 checks/sec

This is read-write balanced at the fetch layer, but heavily write-skewed at the link extraction layer (30 writes per page fetched).

### Peak load multipliers

- News event: crawl traffic spikes 10x for 15 minutes when a major story breaks (indexers request urgent re-crawl of news sites)
- New domain onboarding: when a popular domain is added to the seed list, all its pages get enqueued at once — can be millions of URLs in seconds

### First bottleneck analysis

At 5,000 pages/sec peak:

```
What breaks first at 10x load (50,000 pages/sec)?

1. Fetcher bandwidth: 50,000 * 250 KB = 12.5 GB/sec outbound
   A single 40 Gbps NIC handles 5 GB/sec. Need 3+ machines per rack.

2. URL dedup: 50,000 * 30 = 1.5M Bloom filter checks/sec
   Redis can handle 500K ops/sec per shard. Need 3 Redis shards.

3. DNS: 50,000 unique domains/sec means 50,000 DNS lookups/sec
   A single DNS resolver handles ~10K queries/sec. Need DNS caching + resolver pool.

4. Content store write IOPS:
   50,000 writes/sec * 250 KB = requires object storage (not a single disk)

Winner: DNS is the first bottleneck. It is invisible until you hit scale.
```

### Design target

- Sustained throughput: 2,000 pages/sec (with headroom)
- Peak: 10,000 pages/sec (5x burst, 10 minutes max)
- Graceful degradation: if content store is slow, fetcher drops to 500 pages/sec; URL frontier continues filling; content store catches up

---

## Phase 4: Non-Functional Requirements (Minutes 21-26)

### Latency targets

- Fetch latency per page: p50 = 300ms, p99 = 5s (network-bound, not a user-facing system)
- URL dedup check: p99 < 5ms (Bloom filter in memory)
- robots.txt lookup: p99 < 10ms (from cache); 500ms if cache miss (live HTTP fetch)
- URL enqueue: p99 < 20ms (Kafka append)

### Availability target

- Crawler availability: 99.9% (8.7 hours downtime/year is acceptable — this is not a user-facing service)
- Content store: 99.99% (losing crawled content is expensive — re-crawl costs time)
- If the crawler goes down for 1 hour, we simply haven't crawled ~6M pages. They get crawled in the next cycle. No data loss.

### Consistency model

- URL dedup: **eventual consistency** is acceptable. If a URL is crawled twice because of a Bloom filter race condition, we just store two copies and deduplicate at the content layer. The cost is wasted bandwidth, not a correctness failure.
- Content store: **strong durability** — once we write a page, it must not be lost. Use replication factor 3.
- Frontier queue: **at-least-once delivery** — if a URL is delivered twice, the dedup filter catches it. We do not need exactly-once in the queue.

### Durability requirements

- Crawled content: replicated 3 ways, stored on persistent disk (not ephemeral)
- URL visit log: must survive fetcher machine failure — stored in Kafka with log retention, not in fetcher memory

### Explicit trade-offs stated out loud

> "I am choosing a Bloom filter for URL dedup. This gives O(1) lookup with false positives (~1% rate) but no false negatives. A 1% false positive means we will occasionally re-crawl a URL we already have — that is acceptable waste. The alternative (a full distributed hash set) uses 20x more memory for zero false positives. Not worth it."

> "I am choosing eventual consistency for the URL frontier. A URL might be enqueued twice if two fetchers discover the same link concurrently. The dedup filter handles this. Strong consistency here would require distributed locking, which adds latency to every link enqueue — not worth it at 50K enqueues/sec."

---

## Phase 5: Assumptions and Constraints (Minutes 26-29)

### Assumptions (things I believe are true — correct me if wrong)

- A1: Pages are primarily HTML. PDF and XML are supported but minority.
- A2: The crawler uses a single user-agent string (Googlebot or similar). Sites may serve different content to different user-agents — we assume we get the public-facing HTML.
- A3: The seed URL list is given (top 10M domains from a prior crawl or Alexa-style ranking). The crawler does not need to discover the first URLs from scratch.
- A4: HTTPS certificate validation is standard — we reject self-signed certs.
- A5: Pages that require login are out of scope. If a page returns a login redirect, we mark it as "requires-auth" and skip.

### Constraints (given, not chosen)

- C1: robots.txt must be respected by law (in some jurisdictions) and by industry norm. Non-compliance can result in legal action and IP bans.
- C2: Single datacenter deployment. No cross-DC coordination.
- C3: Budget: approximately 500 fetcher machines at 10 Gbps each. Total outbound bandwidth ~5 Tbps.

### Simplifications (my choices — I can design these if needed)

- S1: I am using a static revisit schedule (news=hourly, e-commerce=daily, static=weekly) rather than an ML-driven adaptive schedule. The adaptive version is an L6 extension.
- S2: JavaScript-rendered pages (SPAs) are treated as empty content. The crawler fetches raw HTML only. A Puppeteer/headless-browser fleet is mentioned as an extension.
- S3: URL priority is based on domain authority (pre-computed, updated weekly) rather than real-time PageRank. Simpler to implement, slightly less optimal.

---

## Architecture Design — HLD (Minutes 29-42)

### Opening analogy

Imagine a library where, instead of waiting for books to arrive, you send out thousands of postal workers to visit every bookstore, library, and home in the world simultaneously. Each worker picks up books, makes a photocopy, and sends the copy back to headquarters. Headquarters organizes the copies. The workers never visit the same address twice (they have a shared list of addresses already visited). And the workers are polite — they never knock on the same door more than once per minute.

That is a web crawler. Fetchers are the postal workers. The URL frontier is the shared address list. The content store is the copy archive at headquarters.

### Full HLD ASCII diagram

```
                          [Seed URL List]
                               |
                               v
+-----------------------------------------------------------+
|                    URL FRONTIER SERVICE                    |
|  (Kafka topics, partitioned by domain hash)               |
|  [Priority Queue] --> [Per-Domain FIFO Queues]            |
|  Stateful | Kafka cluster, 24 brokers, RF=3               |
+-----------------------------------------------------------+
         |                          ^
         | (next URL batch)         | (discovered URLs, filtered)
         v                          |
+---------------------+    +------------------------+
|   FETCHER POOL      |    |   URL DEDUP FILTER     |
|   1000 workers      |    |   (Bloom filter)        |
|   Stateless         |    |   Redis cluster, 3 shards|
|   HTTP/HTTPS client |    |   1.25 GB RAM total     |
|   DNS cache local   |    |   Stateful              |
+---------------------+    +------------------------+
         |                          ^
         |  (raw HTML)              | (extracted URLs)
         v                          |
+---------------------+    +------------------------+
|  ROBOTS.TXT CACHE   |    |   LINK EXTRACTOR       |
|  Redis, 24hr TTL    |    |   Stateless            |
|  500M entries       |    |   Parses HTML, finds   |
|  Stateful           |    |   <a href> tags        |
+---------------------+    |   Normalizes URLs      |
         |                 +------------------------+
         | (robots.txt check before every fetch)     ^
         |                                           |
         v                                           |
+-----------------------------------------------------------+
|                   CONTENT STORE                           |
|  Object storage (S3-compatible), RF=3                    |
|  Keyed: SHA256(normalized_url) + timestamp               |
|  35 TB/day writes                                        |
|  Stateful                                                |
+-----------------------------------------------------------+
         |
         | (parsed content stream)
         v
+-----------------------------------------------------------+
|              DOWNSTREAM CONSUMERS                         |
|  [Search Indexer]  [PageRank Pipeline]  [Spam Detector] |
|  [Freshness Monitor]  [Analytics]                        |
|  (separate systems, not designed here)                   |
+-----------------------------------------------------------+

+-----------------------------------------------------------+
|  SCHEDULER / REVISIT SERVICE                              |
|  Reads: content change frequency from history            |
|  Writes: re-enqueue URLs to frontier on schedule         |
|  Stateful: SQLite/Postgres schedule table               |
+-----------------------------------------------------------+

+-----------------------------------------------------------+
|  CRAWL COORDINATOR                                        |
|  Domain blocklist management                             |
|  Crawl health dashboard                                  |
|  Robots.txt refresh trigger                              |
|  Stateful: Postgres                                      |
+-----------------------------------------------------------+
```

### Component responsibilities table

```
+-------------------+--------------------------------+-----------+------------------+
| Component         | Responsibility                 | Stateful? | Scale target     |
+-------------------+--------------------------------+-----------+------------------+
| URL Frontier      | Queue of URLs to crawl,        | YES       | 50K enqueues/sec |
|                   | per-domain FIFO with priority  |           | 24 Kafka brokers |
+-------------------+--------------------------------+-----------+------------------+
| Fetcher Pool      | HTTP fetch, robots.txt check,  | NO        | 1000 workers     |
|                   | rate limiting, DNS cache       |           | 2,000 fetches/sec|
+-------------------+--------------------------------+-----------+------------------+
| URL Dedup Filter  | Bloom filter: seen this URL?   | YES       | 50K checks/sec   |
|                   | False positive OK, no FN       |           | 3 Redis shards   |
+-------------------+--------------------------------+-----------+------------------+
| Robots.txt Cache  | Cache robots.txt per domain,   | YES       | 500M entries     |
|                   | 24hr TTL, refresh on expire    |           | 1 Redis cluster  |
+-------------------+--------------------------------+-----------+------------------+
| Link Extractor    | Parse HTML, extract <a href>,  | NO        | 2,000 pages/sec  |
|                   | normalize URLs, filter         |           | Stateless pool   |
+-------------------+--------------------------------+-----------+------------------+
| Content Store     | Raw HTML archive, keyed by     | YES       | 35 TB/day        |
|                   | URL hash + timestamp           |           | Object storage   |
+-------------------+--------------------------------+-----------+------------------+
| Scheduler         | Revisit scheduling, track      | YES       | 1M URLs/day      |
|                   | content change frequency       |           | Postgres         |
+-------------------+--------------------------------+-----------+------------------+
| Crawl Coordinator | Admin, blocklist, health       | YES       | Low traffic      |
|                   | monitoring, alerts             |           | Postgres         |
+-------------------+--------------------------------+-----------+------------------+
```

### Write path (discovering and storing a new page)

```
Step 1: Scheduler reads frontier
        [Scheduler] reads next batch of URLs from Kafka frontier topic
        Applies per-domain rate limit: is domain X under 1 req/sec? Yes -> proceed
        Assigns URL to available fetcher worker

Step 2: Fetcher pre-checks
        [Fetcher] checks Robots.txt Cache for domain
        If not cached: fetch domain.com/robots.txt, cache it 24hrs
        If URL is disallowed by robots.txt: mark URL as "robots-blocked", STOP
        If URL is allowed: proceed

Step 3: Fetcher downloads page
        [Fetcher] opens HTTP connection to URL
        Sets User-Agent: Googlebot/2.1
        Sets If-Modified-Since if we have a prior ETag for this URL
        Reads response up to 10 MB limit
        If 301/302: follow redirect (max 5 hops), record redirect chain
        If 404/410: mark URL as dead, STOP
        If 200: proceed

Step 4: Content dedup check
        [Fetcher] compute SHA256 of response body
        Check Content Store: have we seen this exact hash before?
        If yes (near-duplicate): store metadata only, skip full content write
        If no: write full HTML to Content Store

Step 5: Write to Content Store
        [Content Store] stores: URL, timestamp, HTTP status, headers, raw HTML
        Key: SHA256(normalized_url) + epoch_second
        Object storage write (async, acknowledged)

Step 6: Link extraction
        [Link Extractor] parses HTML for <a href="..."> tags
        Resolves relative URLs: /page -> https://example.com/page
        Filters: drop mailto:, javascript:, tel:, data: URIs
        Normalizes: lowercase scheme/host, remove #fragment, sort query params
        Output: list of absolute normalized URLs

Step 7: URL dedup and enqueue
        For each extracted URL:
          [Dedup Filter] checks Bloom filter: seen this URL?
          If YES (or false positive): discard URL
          If NO: add URL to Bloom filter, enqueue to Frontier Kafka topic
```

```
[Scheduler] --> [Fetcher] --> (robots.txt check) --> (HTTP fetch)
                    |
                    v
              [Content Store] <-- write raw HTML
                    |
                    v
             [Link Extractor] --> extracted URLs
                    |
                    v
             [Dedup Filter] --> (seen? discard : add to filter)
                    |
                    v
             [URL Frontier] --> (enqueue for future crawl)
```

### Read path (delivering URLs to fetch)

```
Step 1: Scheduler polls frontier
        [Scheduler] reads from Kafka consumer group "fetcher-pool"
        Kafka delivers URLs ordered by topic partition (domain hash)
        Rate limiter checks per-domain bucket before delivering URL

Step 2: Rate limit gate
        Each domain has a token bucket: refills at 1 token/sec
        URL for domain X: consume 1 token from X's bucket
        If bucket empty: delay URL 1 second, try next domain

Step 3: Priority ordering
        Frontier has two tiers:
        Tier 1 (high priority): news sites, high-PageRank domains
        Tier 2 (normal): everything else
        Fetchers always drain Tier 1 first, then Tier 2

Step 4: Deliver to fetcher
        Scheduler sends URL to fetcher worker (from pool)
        Fetcher worker fetches, returns result
        Result triggers Steps 4-7 from write path above
```

### Key design decisions

```
+------------------+----------------------------+------------------+--------------------+
| Decision         | Why chosen                 | Rejected         | Trade-off          |
+------------------+----------------------------+------------------+--------------------+
| Kafka for        | At 50K enqueues/sec, Kafka | Redis list       | Kafka has higher   |
| URL frontier     | handles it with RF=3 and   |                  | ops overhead than  |
|                  | log durability. Log gives  |                  | Redis but gives    |
|                  | replay for free.           |                  | durability + replay|
+------------------+----------------------------+------------------+--------------------+
| Bloom filter     | 1B URLs fits in 1.25 GB    | Full hash set    | ~1% false positive |
| for URL dedup    | RAM with Bloom. Hash set   | (requires 20 GB) | means ~10M URLs    |
|                  | needs 20 GB+ for same set. |                  | re-crawled.        |
|                  |                            |                  | Acceptable waste.  |
+------------------+----------------------------+------------------+--------------------+
| Per-domain FIFO  | Ensures politeness without | Global FIFO      | Increases frontier |
| queues           | a separate rate limiter    |                  | complexity. A      |
|                  | process. Domain batching   |                  | global FIFO would  |
|                  | also improves DNS cache    |                  | hammer one domain  |
|                  | efficiency.                |                  | if it has many URLs|
+------------------+----------------------------+------------------+--------------------+
| Object storage   | 35 TB/day writes need      | HDFS             | Object storage is  |
| for content      | horizontally scalable,     |                  | slightly slower    |
|                  | cheap, durable storage.    |                  | than HDFS but far  |
|                  | S3-compatible APIs are     |                  | easier to operate  |
|                  | industry standard.         |                  | at this scale.     |
+------------------+----------------------------+------------------+--------------------+
| Token bucket     | Allows burst (domain can   | Fixed rate       | Slightly more      |
| rate limiting    | have 5-token burst) while  | (leaky bucket)   | complex to         |
|                  | averaging 1 req/sec.       |                  | implement but more |
|                  |                            |                  | realistic behavior.|
+------------------+----------------------------+------------------+--------------------+
```

---

## Component-Level Design: Deep Dives

### Component 1: URL Frontier (the heart of the crawler)

**Analogy:** Imagine a to-do list that is organized by two things: how urgent the task is, and who owns it. You have a priority section (urgent tasks first) and within each priority, tasks are grouped by owner so you do not bother the same person twice in a row.

The URL frontier is exactly this: URLs organized by priority tier (importance) and grouped by domain (owner) to ensure politeness.

**Internal structure:**

```
                    [URL Frontier]
                          |
          +---------------+---------------+
          |                               |
   [Tier 1 Kafka Topic]          [Tier 2 Kafka Topic]
   High-priority domains          Normal domains
   (news, top-100K sites)         (everything else)
          |                               |
   Partitioned by domain_hash     Partitioned by domain_hash
          |                               |
   Partition 0: google.com         Partition 0: example.com
   Partition 1: nytimes.com        Partition 1: blog123.com
   Partition 2: bbc.com            Partition 2: smallsite.net
   ...                             ...

Each partition = one domain's FIFO queue
Consumer reads partition P -> all URLs for that domain, in order
```

**Why partition by domain hash?**
- Kafka guarantees ordering within a partition
- Consumer processing partition P = processing one domain at a time
- Rate limiter knows: I am processing domain X, I must wait 1 second between messages from this partition
- No distributed coordination needed for per-domain rate limiting

**Pseudocode for enqueue:**

```
function enqueue_url(url):
    normalized = normalize(url)
    domain = extract_domain(normalized)
    priority = lookup_domain_priority(domain)  // "high" or "normal"
    partition = hash(domain) % NUM_PARTITIONS
    
    if priority == "high":
        kafka.produce(topic="frontier-tier1", partition=partition, value=normalized)
    else:
        kafka.produce(topic="frontier-tier2", partition=partition, value=normalized)
```

**Pseudocode for dequeue with rate limiting:**

```
function fetch_next_url():
    // Always drain Tier 1 first
    url = kafka.poll(topic="frontier-tier1", timeout=100ms)
    if url == null:
        url = kafka.poll(topic="frontier-tier2", timeout=100ms)
    
    if url == null:
        return null  // no work available
    
    domain = extract_domain(url)
    wait_for_token(domain)  // blocks until domain bucket has capacity
    return url

function wait_for_token(domain):
    bucket = get_token_bucket(domain)  // from Redis
    while bucket.tokens == 0:
        sleep(100ms)
        bucket.refill(elapsed_time)
    bucket.tokens -= 1
    save_token_bucket(domain, bucket)
```

**Failure mode:** If Kafka brokers go down, the frontier stops delivering URLs. Fetchers idle. When Kafka recovers, the frontier resumes from the committed consumer offset — no URLs are lost or re-processed (Kafka commits guarantee this). Fetchers detect idle time and alert SRE if idle > 60 seconds.

---

### Component 2: Bloom Filter URL Deduplication

**Analogy:** Imagine you have a bingo card with 10 billion squares. When you see a new URL, you use 7 magic markers (7 hash functions) to mark 7 specific squares. To check if you have seen a URL: use the same 7 markers, check if all 7 squares are marked. If all 7 are marked, you have probably seen it (with ~1% chance of error). If even one square is unmarked, you definitely have not seen it.

This is a Bloom filter. It never says "definitely yes" — only "probably yes" or "definitely no."

**Internal diagram:**

```
URL: "https://example.com/page"
         |
    [7 hash functions]
         |
    h1 -> bit 1,234,567
    h2 -> bit 4,892,001
    h3 -> bit 9,023,445
    h4 -> bit 3,211,987
    h5 -> bit 7,654,321
    h6 -> bit 2,345,678
    h7 -> bit 8,901,234

    Bit array (1.25 GB = 10 billion bits):
    [0,0,...,1,...,0,...,1,...,0,...,1,...,1,...,0,...,1,...,1,...]
                  ^         ^         ^   ^              ^    ^
                h1=1      h2=1      h3=1 h4=1           h5=1 h7=1
    h6 bit = 0? -> NOT SEEN (definitely)
    All bits = 1? -> PROBABLY SEEN (1% false positive chance)
```

**Size calculation:**

```
n = 1 billion URLs to track
p = 0.01 (1% false positive rate)

m = -n * ln(p) / (ln(2))^2
m = -1B * ln(0.01) / 0.480
m = -1B * (-4.605) / 0.480
m = 9.59 billion bits
m = 1.2 GB RAM

k = (m/n) * ln(2) = 9.59 * 0.693 = 6.64 -> round up to 7 hash functions
```

**Distributed implementation:**
- Redis BITSET operations: `GETBIT` and `SETBIT` are O(1)
- 1.25 GB fits in a single Redis instance, but we shard across 3 for availability
- Shard selection: `shard = h0(url) % 3`, then hash functions h1-h7 run on that shard
- Atomic: `SETBIT` in Redis is atomic, so concurrent writes do not corrupt the filter

**False positive consequence:** About 10 million URLs out of 1 billion will be mistakenly skipped. These are legitimately new pages the crawler refuses to visit because the filter says "probably seen." The cost: 10 million missed pages per crawl cycle. These will be discovered in the next cycle when the filter is reset. Acceptable trade-off.

**Filter reset:** At the start of each crawl cycle (every 7 days), the Bloom filter is reset to all zeros and rebuilt as pages are crawled. This prevents the filter from filling up and degrading to 100% false positive rate over time.

**Failure mode:** If Redis crashes and filter state is lost, all URLs appear unseen — the crawler will re-crawl many already-visited pages. Content store dedup (SHA256 content hash) acts as a second layer: even if URLs are re-fetched, identical content is stored only once.

---

### Component 3: Fetcher Pool (the HTTP download workers)

**Analogy:** Think of the fetcher pool as a team of librarians who go out to collect books. Each librarian can only carry 10 books at a time (connection pool), checks the store's "no soliciting" sign before entering (robots.txt), and is polite enough not to knock twice within the same minute (rate limiter). They cache the directions to each address (DNS cache) so they are not constantly calling information.

**Internal diagram:**

```
         [Scheduler delivers URL]
                    |
                    v
+-------------------------------------------+
|              FETCHER WORKER               |
|                                           |
|  1. robots.txt check                      |
|     cache hit? -> use cached ruling       |
|     cache miss? -> fetch robots.txt now   |
|     disallowed? -> skip URL, log it       |
|                                           |
|  2. DNS resolution                        |
|     local DNS cache (TTL 300s)?           |
|     cache hit? -> use cached IP           |
|     cache miss? -> DNS resolver lookup    |
|                                           |
|  3. HTTP fetch                            |
|     TCP connect (timeout: 5s)             |
|     TLS handshake (HTTPS)                 |
|     HTTP GET + headers                    |
|     Read response (timeout: 30s)          |
|     Size limit: 10 MB                     |
|                                           |
|  4. Handle response codes                 |
|     200: proceed to parse                 |
|     301/302: follow redirect (max 5)      |
|     304 Not Modified: skip content write  |
|     404/410: mark URL dead               |
|     429 Too Many Requests: backoff 60s   |
|     5xx: retry 3x with exponential       |
|                                           |
|  5. Output: (url, status, html_body,      |
|             headers, redirect_chain)      |
+-------------------------------------------+
```

**Pseudocode for one fetch:**

```
function fetch_page(url):
    domain = extract_domain(url)
    
    // Step 1: robots.txt check
    ruling = robots_cache.get(domain)
    if ruling == null:
        robots_txt = http_get(domain + "/robots.txt", timeout=5s)
        ruling = parse_robots(robots_txt, user_agent="Googlebot")
        robots_cache.set(domain, ruling, ttl=86400)
    
    if ruling.disallows(url):
        return Result(status="robots-blocked")
    
    // Step 2: DNS
    ip = dns_cache.get(domain)
    if ip == null:
        ip = dns_resolver.resolve(domain)
        dns_cache.set(domain, ip, ttl=300)
    
    // Step 3: HTTP
    try:
        response = http_get(url, ip=ip, timeout=30s, max_bytes=10MB)
    catch TimeoutError:
        return Result(status="timeout")
    catch TLSError:
        return Result(status="tls-error")
    
    // Step 4: redirects
    if response.status in [301, 302]:
        redirect_url = response.headers["Location"]
        if redirect_count >= 5:
            return Result(status="too-many-redirects")
        return fetch_page(redirect_url, redirect_count + 1)
    
    // Step 5: return
    return Result(status="ok", body=response.body, headers=response.headers)
```

**Failure mode:** If a fetcher worker crashes mid-fetch, the URL is not committed from Kafka — the consumer offset is not advanced. On worker restart, Kafka re-delivers the URL. This is the "at-least-once" guarantee. The content store's SHA256 dedup ensures we do not write duplicate content.

**Scaling the fetcher pool:**
- 1000 fetcher workers running concurrently (async I/O, not threads)
- Each worker handles 2 concurrent connections = 2000 concurrent fetches
- Network: each worker uses ~500 KB/s on average = 500 MB/s total = well within 10 Gbps NIC

---

### Component 4: URL Normalization

**Analogy:** Imagine two people writing the same address differently: "123 Main St." vs "123 Main Street" vs "123 MAIN ST". A mail carrier needs to recognize these are the same address. URL normalization does the same — it converts URLs to a single canonical form so duplicates are detected.

**Normalization rules (applied in order):**

```
Input: "HTTP://Example.COM/Path?b=2&a=1#fragment"

Step 1: Lowercase scheme and host
    -> "http://example.com/Path?b=2&a=1#fragment"

Step 2: Remove fragment (#...)
    -> "http://example.com/Path?b=2&a=1"

Step 3: Lowercase path
    -> "http://example.com/path?b=2&a=1"

Step 4: Sort query parameters alphabetically
    -> "http://example.com/path?a=1&b=2"

Step 5: Remove default ports (80 for http, 443 for https)
    Example.com:80/path -> example.com/path

Step 6: Remove trailing slash on root
    example.com/ -> example.com

Step 7: Decode percent-encoding for unreserved chars
    example.com/caf%C3%A9 -> example.com/café

Step 8: Remove session IDs and tracking params
    ?sessionid=abc123 -> removed
    ?utm_source=google -> removed

Output: "http://example.com/path?a=1&b=2"
```

**Why sorting query params matters:**
`/search?q=hello&lang=en` and `/search?lang=en&q=hello` are the same page. Without sorting, both would pass through the Bloom filter as different URLs and be crawled twice.

**Why remove tracking params:**
`/page?utm_source=twitter` and `/page?utm_source=email` are the same content. Without this, every marketing campaign link to the same page generates a new crawl job.

---

### Component 5: Revisit Scheduler

**Analogy:** Imagine a newspaper delivery service. You deliver the New York Times every morning (high frequency), deliver a monthly magazine once a month (low frequency), and for a book you bought once, you do not deliver it again (static content). The scheduler decides each URL's delivery frequency based on how often its content changes.

**Change detection:**

```
When we crawl a page for the second time:
  prev_hash = stored SHA256 from last crawl
  curr_hash = SHA256 of new content
  
  if curr_hash == prev_hash:
      content_unchanged = true
      // Slow down: next visit is further away
  else:
      content_changed = true
      change_detected = true
      // Maintain or increase frequency

change_frequency = changes / visits
// Over 10 visits, if page changed 7 times: high frequency
// Over 10 visits, if page changed 1 time: low frequency
```

**Revisit schedule buckets:**

```
+-------------------+--------------------+------------------+
| Frequency class   | Revisit interval   | Example          |
+-------------------+--------------------+------------------+
| Breaking news     | 15 minutes         | bbc.com/news/live|
| News / blog       | 1 hour             | nytimes.com      |
| E-commerce        | 1 day              | amazon.com/p/xyz  |
| Reference / wiki  | 7 days             | wikipedia.org    |
| Static / docs     | 30 days            | docs.example.com |
| Dead / 404        | Never              | (removed)        |
+-------------------+--------------------+------------------+
```

**Implementation:** Postgres table `revisit_schedule`:
```
url_hash (PK), next_crawl_at (indexed), frequency_class, last_crawl_at, change_count, visit_count
```

Scheduler runs every minute: `SELECT * FROM revisit_schedule WHERE next_crawl_at <= NOW() LIMIT 10000`. Enqueues results to Kafka frontier. Updates `next_crawl_at = NOW() + interval` after enqueue.

---

## Deep Concept Explanations (SSE Cross-Questioning Targets)

### Concept 1: Bloom Filter — the math behind the magic

An interviewer will probe: "How does a Bloom filter actually work? What makes it probabilistic? Can you walk me through the math?"

**The core idea:**

A Bloom filter is a bit array of size m, initially all zeros. When you insert an element, you compute k different hash functions on it. Each hash function returns a position between 0 and m-1. You set those k bits to 1. To check if an element is in the set: compute the same k hash functions, check if all k bits are 1. If any bit is 0: definitely not in the set. If all bits are 1: probably in the set (but might be a coincidental collision).

**Why can it only have false positives, never false negatives?**

Inserting an element sets specific bits to 1. Bits never go back to 0. So if you inserted URL X, all k bits for URL X are permanently 1. Querying URL X will always find all k bits = 1. Therefore: if X was inserted, query always returns "yes." No false negatives.

False positives happen when k bits for URL Y happen to all be set to 1 — not because Y was inserted, but because other URLs set those same bit positions. Y was never inserted, but all its bit positions happen to be 1 from other URLs.

**The math:**

```
After inserting n elements into a filter of m bits:
Probability that any single bit is still 0:
    (1 - 1/m)^(kn) ≈ e^(-kn/m)

Probability that all k bits for a new element are 1 (false positive):
    p = (1 - e^(-kn/m))^k

To minimize p, the optimal number of hash functions:
    k = (m/n) * ln(2) ≈ 0.693 * (m/n)

At optimal k, false positive rate simplifies to:
    p = (1/2)^k = (ln(2))^(m/n * ln(2))

For our numbers (n=1B, p=0.01):
    m = 9.59B bits = 1.2 GB
    k = 7 hash functions
```

**The trade-off expressed clearly:**

More memory (larger m) = lower false positive rate. More hash functions (larger k) = more computation per lookup but lower false positive. The Bloom filter is essentially buying accuracy by trading RAM.

---

### Concept 2: Politeness and Per-Domain Rate Limiting

An interviewer will probe: "Why can you not just crawl as fast as possible? What is the right way to implement politeness?"

**Why politeness matters:**

A web crawler without politeness is functionally a DDoS attack. If you make 1000 requests per second to `example.com`, you will overwhelm their servers, get your IP banned, potentially cause legal liability (in some jurisdictions), and violate the robots.txt `Crawl-delay` directive.

Politeness rules:
1. Never exceed 1 request/second to any single domain (unless Crawl-delay allows more)
2. Respect `Crawl-delay` directive in robots.txt (some sites request 10s or 60s delay)
3. Respect `Retry-After` header in 429 (Too Many Requests) responses
4. Keep TCP connections alive when re-visiting the same domain in quick succession (reduce connection overhead, also more polite than opening fresh TCP for every request)

**Token bucket vs leaky bucket:**

```
Token bucket (what we use):
  - Bucket starts with capacity = C tokens
  - Refills at rate R tokens/sec
  - Each request consumes 1 token
  - If bucket has tokens: process immediately
  - If bucket empty: wait until refill

Leaky bucket:
  - Requests enter a queue
  - Queue drains at fixed rate R
  - Excess requests are queued or dropped

Why token bucket:
  - Allows bursting: if domain.com has not been visited in 10 seconds,
    bucket has 10 tokens -> you can make 10 requests quickly
  - Leaky bucket forces even spacing even after long idle periods
  - For crawlers, bursting is useful: if we just discovered 100 new pages on
    example.com, we want to fetch them quickly (in 100 seconds) not slowly
```

**Per-domain implementation in Redis:**

```
domain = "example.com"
key = "rate_limit:" + domain

// Atomic Redis script (Lua, runs atomically):
tokens = GET key
if tokens == null:
    tokens = 10  // initial capacity
last_refill = time.now()
else:
    elapsed = time.now() - GET (key + ":last_refill")
    tokens = min(10, tokens + elapsed * 1.0)  // refill at 1/sec, max 10

if tokens >= 1:
    SET key (tokens - 1)
    SET (key + ":last_refill") time.now()
    return "allowed"
else:
    return "wait"
```

---

### Concept 3: URL Normalization and Crawl Traps

An interviewer will probe: "How do you detect and handle crawl traps? Give me a specific example."

**What is a crawl trap?**

A crawl trap is a set of URLs that generates an infinite or very large number of unique-looking URLs, all pointing to essentially the same content (or no content). Crawlers without trap detection get stuck downloading the same site forever.

**Types of crawl traps:**

```
Type 1: Calendar/date navigation
  /calendar/2024/01 -> has links to /calendar/2024/01/01
  /calendar/2024/01/01 -> has links to /calendar/2023/12/31
  /calendar/2023/12/31 -> has links to /calendar/2023/12/30
  -> infinite backward crawl through history

Type 2: Session ID in URL
  /page?sessionid=abc123 -> links to /page?sessionid=def456
  /page?sessionid=def456 -> links to /page?sessionid=ghi789
  -> infinite unique URLs, all the same content

Type 3: Search result pagination
  /search?q=cats&page=1 -> links to /search?q=cats&page=2
  /search?q=cats&page=2 -> links to /search?q=cats&page=3
  -> /search?q=cats&page=9999999

Type 4: Adversarial trap (anti-crawler)
  A site generates new unique URLs in its <a href> tags specifically to
  exhaust crawler resources (link spam, crawler poisoning)
```

**Detection and mitigation:**

```
Defense 1: URL depth limit
  Track hop count from seed URL
  If hop_count > 10: discard the URL
  Prevents: calendar traps, deep recursive navigation

Defense 2: Per-domain URL cap
  Track how many URLs from domain X are in the queue
  If count > 100,000: stop accepting new URLs from domain X
  Prevents: adversarial link generation, site-wide bulk crawl

Defense 3: Normalized URL dedup
  Remove session IDs, UTM params, sorted query params
  Collapses many trap-generated URLs into one canonical URL
  Prevents: session ID traps

Defense 4: Repeated path segment detection
  /a/b/c/d/a/b/c/d/a/b/c/d -> contains repeating /a/b/c/d
  If path contains >3 repeated segments: discard
  Prevents: recursive directory traps

Defense 5: URL length limit
  If URL length > 2048 chars: discard
  Prevents: parameter-stuffed URLs
```

**Specific example for interview:**

> "I would detect a calendar trap like this: normalize the URL to remove date parameters that follow a /YYYY/MM/DD pattern. Then apply a depth limit — if we have already gone 5 hops into `example.com/calendar/...`, stop following calendar-pattern links from that domain. Additionally, if domain example.com has contributed 50,000+ URLs to the frontier in 10 minutes, I trigger a domain velocity alert, cap further URL acceptance from that domain, and flag it for manual review."

---

### Concept 4: Content Deduplication with SimHash

An interviewer will probe: "URL dedup isn't enough — the same content can live at different URLs. How do you detect near-duplicate content?"

**Two levels of content dedup:**

Level 1 — Exact duplicate (SHA256):
```
page1 = fetch("http://example.com/page")
page2 = fetch("http://mirror.com/page")
SHA256(page1.body) == SHA256(page2.body)? -> exact duplicate
-> store metadata only, skip content write
```

Level 2 — Near-duplicate (SimHash):
```
Page A: "The quick brown fox jumps over the lazy dog"
Page B: "The quick brown fox jumps over the lazy cat"
These are 97% similar. SHA256 is completely different. SimHash detects this.
```

**How SimHash works:**

```
Step 1: Extract features (shingles)
  Tokenize the page into word n-grams (3-grams):
  "The quick brown", "quick brown fox", "brown fox jumps", ...

Step 2: Hash each feature
  hash("The quick brown") -> 64-bit hash -> look at each bit:
  bit0=1, bit1=0, bit2=1, ... bit63=1

Step 3: Accumulate weights
  For each feature's hash, for each bit position:
    if bit_i == 1: weight[i] += 1
    if bit_i == 0: weight[i] -= 1

Step 4: Final hash
  For each bit position:
    if weight[i] > 0: simhash[i] = 1
    else: simhash[i] = 0

Result: a 64-bit fingerprint for the page
```

**Near-duplicate detection:**

```
Page A simhash: 1010110101010101...
Page B simhash: 1010110101010111...
                                  ^
Hamming distance = 1 (only 1 bit different)
Hamming distance <= 3: considered near-duplicate (>97% similar)
```

**Why not use SimHash for URL dedup?**
SimHash is expensive to compute (requires tokenizing and hashing the full page content). Bloom filter for URL dedup runs before we even fetch the page — zero content cost. SimHash runs after the fetch on the downloaded content.

---

### Concept 5: DNS Caching at Crawler Scale

An interviewer will probe: "You mentioned DNS caching. Walk me through what happens if you don't cache DNS at this scale."

**The DNS problem without caching:**

```
At 2,000 fetches/sec, with 2,000 unique domains per second:
  2,000 DNS queries/sec to external resolvers

A typical DNS resolver handles 10,000-50,000 queries/sec
But round-trip latency to a public DNS resolver (8.8.8.8): 10-50ms
2,000 DNS queries * 30ms average = 60 seconds of DNS latency per second
-> fetchers spend all their time waiting for DNS, not fetching content
-> effective throughput drops to ~200 pages/sec

Also: DNS resolvers rate-limit abusive clients. Google's 8.8.8.8
will throttle you if you send thousands of queries/sec from one IP.
```

**Solution: local DNS cache on each fetcher:**

```
Each fetcher machine runs a local DNS cache (e.g., dnsmasq or a simple TTL hash map):

First request to nytimes.com:
  1. Check local cache: MISS
  2. Query internal DNS resolver (one per datacenter): 5ms round trip
  3. Cache: nytimes.com -> 151.101.65.164 (TTL=300s)
  4. Return cached IP for next 300 seconds

Next 300 requests to nytimes.com (within 300 seconds):
  1. Check local cache: HIT
  2. Return immediately (0ms DNS overhead)

Savings: 299 DNS lookups saved per 5-minute window per domain
```

**Edge case: DNS cache poisoning / stale entries:**

If a domain changes its IP (server migration), all fetchers might connect to the old IP for up to 300 seconds. For most domains this is irrelevant (they keep old IPs accessible during migration). Mitigation: cap DNS cache TTL at 300 seconds regardless of the record's actual TTL.

**Edge case: round-robin DNS:**

Large sites like google.com have hundreds of IPs in their DNS record, returned in rotating order. The crawler should connect to any of the returned IPs and let the site's load balancer handle routing. The crawler does not need to implement connection affinity.

---

### Concept 6: robots.txt Parsing and Compliance

An interviewer will probe: "Walk me through how robots.txt actually works. What are the edge cases?"

**robots.txt format:**

```
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /private/public-page/
Crawl-delay: 2

User-agent: Googlebot
Disallow: /no-google/
Allow: /
Crawl-delay: 1
```

**Parsing rules:**

```
1. User-agent matching: most specific user-agent wins
   - "Googlebot" matches our crawler if we identify as Googlebot
   - "*" is the catch-all if no specific agent matches
   - Rules under the matching agent apply

2. Allow vs Disallow precedence:
   - Most specific path wins: /private/public-page/ (Allow) beats /private/ (Disallow)
   - Specificity = length of the matching prefix

3. Crawl-delay: minimum seconds between requests to this domain
   - Must be honored even if our default rate limit is faster
   - A site saying Crawl-delay: 60 means 1 request per minute

4. Sitemap directive: 
   Sitemap: https://example.com/sitemap.xml
   -> The crawler should parse this sitemap and add all URLs to the frontier
   -> A useful signal for prioritizing fresh, validated URLs
```

**Implementation:**

```
function check_robots(url, user_agent):
    domain = extract_domain(url)
    robots_text = fetch_and_cache_robots(domain, ttl=86400)
    rules = parse_robots(robots_text, user_agent)
    
    // Find matching rule for this URL path
    path = extract_path(url)
    best_match = None
    best_match_length = -1
    
    for rule in rules:
        if path.startswith(rule.prefix):
            if len(rule.prefix) > best_match_length:
                best_match = rule
                best_match_length = len(rule.prefix)
    
    if best_match == None:
        return ALLOWED  // no rule = allowed by default
    
    return best_match.type  // ALLOWED or DISALLOWED
```

**Edge cases:**

```
1. robots.txt does not exist (404):
   -> Treat as "all allowed" (RFC standard)

2. robots.txt returns 5xx:
   -> Temporarily block crawl of this domain, retry in 1 hour
   -> Do NOT treat 5xx as "all blocked" (would deny crawl of healthy sites with a bad robots.txt server)

3. robots.txt is very large (>500 KB):
   -> Some sites have huge robots.txt files (Airbnb: 80KB, Twitter: 68KB)
   -> Parse only the first 500 KB, log a warning

4. robots.txt has syntax errors:
   -> Use lenient parser, ignore unrecognized directives
   -> Never crash; prefer to over-crawl rather than under-crawl on parse error

5. robots.txt for HTTPS vs HTTP:
   -> They are separate files. A site can disallow http:// crawl but allow https://
   -> Fetch robots.txt on the same scheme as the target URL
```

---

## Failure Scenarios and Degradation

### Failure 1: URL Frontier (Kafka) goes down

```
What happens:
  - Fetchers have no URLs to process, go idle
  - Link extractor cannot enqueue new URLs
  - Revisit scheduler cannot enqueue revisit URLs

Cascade:
  - Fetcher workers time out on Kafka poll -> backoff -> retry
  - No downstream effect immediately (content store not affected)

Detection:
  - Alert: kafka_consumer_lag drops to 0 across all topics for > 60s
  - Fetcher idle rate spikes to 100%

Degraded mode:
  - Fetchers go idle. No crawling happens. No user-facing impact (search index
    continues serving stale data, which is its normal operation).

Recovery:
  - Kafka brokers restart, consumers resume from committed offset
  - No URL loss: Kafka's durable log preserves all unconsumed messages
  - Crawl resumes automatically within 2-3 minutes of Kafka recovery
```

### Failure 2: Content Store goes down

```
What happens:
  - Fetchers download pages but cannot write them
  - Fetcher workers accumulate failed write attempts

Options:
  Option A: Drop the content, re-crawl later
    -> Simple, no memory pressure on fetchers
    -> URLs are re-queued to Kafka with delay
    -> Content loss for the failed window (acceptable for non-news)

  Option B: Buffer in fetcher memory (risky)
    -> Fetcher has limited RAM, cannot buffer long
    -> If content store is down for 10 minutes: 10 * 2000 fetches * 250KB = 3 GB
    -> Not viable for extended outages

We choose Option A: drop content on write failure, re-enqueue URL.
```

### Failure 3: Bloom Filter Redis goes down

```
What happens:
  - URL dedup is unavailable
  - All URL checks return "not seen" (fail open: assume unseen)

Impact:
  - URLs that were already crawled get re-queued
  - Crawl duplication rate spikes from 1% (normal false positive) to potentially 50%+
  - Content store receives duplicate writes (SHA256 dedup at content layer catches it)
  - Extra crawl load on target websites (politeness concern)

Detection:
  - Redis connection error rate in fetcher metrics
  - Frontier queue depth grows rapidly (duplicates flooding in)

Degraded mode:
  - Continue crawling with dedup disabled
  - Content store dedup prevents duplicate storage
  - Throttle enqueue rate to 25% of normal to limit duplicate traffic to sites
  - Alert SRE immediately

Recovery:
  - Redis cluster restores from AOF/RDB snapshot (most recent, within 1 minute of state)
  - Or: rebuild Bloom filter by scanning content store (expensive: 12-24 hour process)
  - Pragmatic: restart with empty filter, accept 24 hours of increased duplication
```

### Failure 4: Fetcher worker crashes mid-fetch

```
What happens:
  - Kafka message was received but consumer offset was not committed
  - On worker restart, Kafka re-delivers the URL

Impact:
  - URL is fetched twice at most (once before crash, once after)
  - Content store may receive two writes for the same URL
  - SHA256 dedup in content store deduplicates automatically

No data loss: Kafka at-least-once delivery is the intended behavior here.
```

### Failure 5: Target website blocks our IP

```
What happens:
  - Website starts returning 403 Forbidden or 429 Too Many Requests
  - Or: silently returns empty/garbage HTML (honeypot trap)

Detection:
  - Per-domain HTTP status code monitoring
  - 403 rate spike for a domain: alert

Response:
  - Respect 429 Retry-After header
  - After 3 consecutive 403s: back off 24 hours, alert SRE
  - Check if we violated politeness: did rate limiter malfunction?

The correct response is to back off and respect the site's decision.
We do NOT rotate IPs or use proxies to circumvent blocks —
that violates terms of service and potentially laws.
```

### Blast radius analysis

```
Component failure    | Blast radius                            | Recovery time
---------------------|----------------------------------------|---------------
Kafka broker (1/24)  | 1/24 of frontier throughput            | Auto: 30s
Kafka cluster down   | Full crawl halt                        | Manual: 5-30min
Redis (Bloom) down   | Dedup disabled, 50% duplicate crawl    | Auto: 2-5min
Content store node   | Writes slow, some drops                | Auto: 1-2min
Content store down   | No content stored, re-crawl needed     | Manual: varies
Fetcher machine      | 1/100 of fetcher capacity lost         | Auto: 1min
DNS resolver down    | 10-20% latency increase, cache decay   | Auto: 1min
All fetchers         | Full crawl halt                        | Manual: 5min
```

---

## SSE-Level Brainstorming Questions (Concept-Focused)

These are questions that probe the underlying CONCEPTS, not the design. An SSE interviewer will cross-question you on these.

### Bloom Filter concepts (ask these to a candidate)

1. A Bloom filter can have false positives but never false negatives. Why is the "never false negatives" property guaranteed by the data structure itself?
2. If you insert the same URL into a Bloom filter twice, does the false positive rate change? Why or why not?
3. How do you reset a Bloom filter without rebuilding it from scratch? What data structure allows efficient deletion?
4. If your Bloom filter's false positive rate reaches 50%, what has happened? How would you detect this? (Answer: the filter is full — nearly all bits are 1)
5. The counting Bloom filter supports deletion. What is its space overhead compared to a standard Bloom filter?
6. If you double the number of hash functions (k) in a Bloom filter, what happens to the false positive rate and why?
7. What is the relationship between the Bloom filter and the concept of a probabilistic data structure? Name two other probabilistic data structures used in systems design.
8. Why is MurmurHash or xxHash preferred over MD5/SHA256 for Bloom filter hash functions?

### Token bucket / rate limiting concepts

9. A token bucket allows bursting. If a bucket has capacity C=10 and refill rate R=1/sec, and a domain has been idle for 100 seconds, how many requests can it immediately serve before being rate-limited?
10. What is the difference between a token bucket and a leaky bucket in terms of output traffic shape? Which is smoother?
11. In distributed rate limiting across 10 fetcher workers sharing one per-domain bucket in Redis, what is the race condition risk and how do you handle it atomically?
12. Why is Lua scripting in Redis used for token bucket operations rather than a multi-step GET-then-SET?
13. If a site's robots.txt specifies `Crawl-delay: 0`, what should your crawler do?
14. What happens if two robots.txt directives conflict for the same path — one Allow and one Disallow?

### URL normalization concepts

15. Two URLs differ only in their query parameter order: `/search?lang=en&q=cats` vs `/search?q=cats&lang=en`. After normalization, are they equal? Should they be?
16. What is a URL trap? Give three distinct types and one detection heuristic for each.
17. Why is URL length a useful signal for detecting crawl traps? What is the practical length limit you would apply?
18. The URL `/page#section2` should the fragment be preserved or stripped for dedup? Why?
19. Session IDs in URLs create millions of unique URLs pointing to the same content. How would you detect and strip them if you don't know the parameter name (`?sessionid=` vs `?s=` vs `?sid=`)?

### DNS concepts

20. A fetcher machine has a local DNS cache with TTL=300s. The domain's actual DNS TTL is 60s. The domain migrates servers at t=0. How long until the fetcher connects to the new server?
21. What is negative caching in DNS? Why is it important for a web crawler?
22. Round-robin DNS returns different IPs for the same domain. Should the crawler implement connection affinity (always use the same IP for a domain) or load-spread across all returned IPs? What is the trade-off?
23. What is the difference between A records and CNAME records in DNS? Does your crawler need to handle CNAMEs differently?

### HTTP / robots.txt concepts

24. A site returns `robots.txt` with a 200 status but an empty body. Should you treat this as "all allowed" or "all blocked"? What does the RFC say?
25. If `robots.txt` returns a 5xx error, should you crawl the site or block? What is the reasoning?
26. The HTTP `ETag` and `If-None-Match` headers allow conditional GETs. How would you use these to implement efficient freshness checking without re-downloading unchanged content?
27. What is the difference between `301 Moved Permanently` and `302 Found` in the context of a crawler? Should the crawler update the stored URL after a 301?
28. A page returns `Content-Type: text/html; charset=iso-8859-1` but the actual bytes are UTF-8. How does this affect link extraction?

### Content dedup concepts

29. SimHash is sensitive to the order of words in shingles. Why is a 3-gram (three consecutive words) better than individual words for near-duplicate detection?
30. If two pages are 80% identical in content but completely different in layout (different navigation, different ads), should SimHash treat them as near-duplicates? What does the algorithm actually compute?
31. What is the Hamming distance, and why is it the right distance metric for SimHash comparison rather than Euclidean distance?
32. MinHash is another technique for similarity detection (used in LSH). What problem does MinHash solve that SimHash does not? (Answer: MinHash estimates Jaccard similarity between sets; SimHash estimates cosine similarity of weighted vectors.)

---

## Intern to Staff Progression

### Same problem: "Design a URL deduplication system for 1 billion URLs"

### Intern level

```
Approach: Store all URLs in a database table. Before crawling, do:
  SELECT count(*) FROM visited_urls WHERE url = 'https://example.com/page'

Problem: 50K lookups/sec * 1ms/lookup = OK initially
         1B rows in the table = 100 GB+
         Index scans get slow as table grows
         Full table scan on each lookup: 30-60 seconds per query at scale

The intern knows what the problem is and has a working solution.
The intern does not know what breaks at scale.
```

### L4 (Software Engineer) level

```
Approach: Use Redis with a hash set (SADD / SISMEMBER)
  SISMEMBER visited_urls "https://example.com/page" -> 0 or 1
  SADD visited_urls "https://example.com/page"

Better: O(1) lookup, Redis handles millions of ops/sec

Problem:
  1B URLs * 100 bytes per URL = 100 GB RAM for the hash set
  Redis on a single machine: 32 GB RAM max on typical hardware
  Need 4 Redis shards for 1B URLs

L4 gets the right data structure but does not consider memory cost.
Does not know the formula to size a Bloom filter.
```

### L5 (Senior SWE) level

```
Approach: Bloom filter + Redis BITSET

1. Compute Bloom filter size:
   n=1B, p=0.01 -> m=1.2GB, k=7 hash functions

2. Implement using Redis BITSET:
   Each hash function maps URL to a bit position
   GETBIT / SETBIT for O(1) lookup and insert
   Total RAM: 1.2 GB (vs 100 GB for hash set) -- 83x reduction

3. Handle false positives:
   ~10M URLs re-crawled due to false positives
   Content store SHA256 dedup as second layer

4. Handle reset:
   Reset filter at start of each 7-day crawl cycle

L5 correctly identifies the right algorithm, sizes it, and
handles the false positive consequence.
```

```
Intern approach:
+----------------+     SELECT * FROM      +-------------+
|  Fetcher       | --> visited_urls WHERE  | Postgres    |
|                |     url = '...'         | (100 GB+)   |
+----------------+                        +-------------+

L4 approach:
+----------------+     SISMEMBER          +-------------+
|  Fetcher       | -->  visited_urls '...' | Redis hash  |
|                |                        | (100 GB RAM)|
+----------------+                        +-------------+

L5 approach:
+----------------+  7 x GETBIT            +-------------+
|  Fetcher       | -->  bit_array '...'    | Redis BITSET|
|                |                        | (1.2 GB RAM)|
+----------------+                        +-------------+
                  all 7 bits = 1?
                  -> probably seen (1% FP)
                  any bit = 0?
                  -> definitely not seen
```

### L6 (Staff) level

```
Approach: Sharded Bloom filter + circuit breaker + adaptive reset

1. Sharded Bloom filter:
   Shard by URL hash -> 10 shards of 120 MB each
   Each shard independently readable/writable
   One shard failure: 10% false negative risk, not total outage

2. Count-Min Sketch alongside Bloom filter:
   Track approximate URL frequency (how many times each URL has been seen)
   High-frequency re-attempted URLs -> possible crawl loop detection
   Evict stuck URLs from the dedup filter if seen 100+ times (crawl trap)

3. Persistent Bloom filter:
   Bloom filter state backed to RocksDB daily
   After Redis failure: restore from RocksDB snapshot (1 minute vs 12-hour rebuild)
   Warm startup without full re-crawl

4. Adaptive reset threshold:
   Do not reset filter on a fixed 7-day schedule
   Reset when false positive rate exceeds 5% (estimate from probe queries)
   Measure: send N known-unseen synthetic URLs, count false positives
   This prevents resetting early (waste) and late (degraded accuracy)

L6 thinks about failure isolation (sharding), recovery speed
(persistent backup), and adaptive behavior (threshold-based reset).
```

---

## L5 vs L6 Calibration Table

```
+---------------------+---------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)            | L6 (Staff)                     |
+---------------------+---------------------------+--------------------------------+
| URL dedup           | Bloom filter, correct      | Sharded BF, persistent backup  |
|                     | sizing, false positive     | Count-Min Sketch for loop      |
|                     | consequence stated         | detection, adaptive reset      |
+---------------------+---------------------------+--------------------------------+
| Politeness          | Token bucket per domain,  | Multi-level: per-domain +      |
|                     | 1 req/sec, robots.txt     | per-IP + adaptive Crawl-delay  |
|                     | compliance                | Learning-based: observe 429s   |
|                     |                           | and self-tune rate             |
+---------------------+---------------------------+--------------------------------+
| URL frontier        | Kafka, partitioned by     | Kafka + priority tiering       |
|                     | domain, tier 1 vs tier 2  | PageRank-weighted scheduling   |
|                     |                           | Cross-DC frontier with geo     |
|                     |                           | routing and DC affinity        |
+---------------------+---------------------------+--------------------------------+
| Freshness           | Static schedule (news=1h, | ML model: predict change time  |
|                     | e-com=1d, static=7d)      | from change history, content   |
|                     |                           | type, site type, traffic       |
+---------------------+---------------------------+--------------------------------+
| JS rendering        | Out of scope              | Puppeteer fleet, GPU-backed    |
|                     |                           | headless browsers, JS-site     |
|                     |                           | detection heuristics           |
+---------------------+---------------------------+--------------------------------+
| Content dedup       | SHA256 exact dedup        | SHA256 + SimHash near-dedup    |
|                     |                           | + canonical URL inference      |
|                     |                           | + duplicate cluster tracking   |
+---------------------+---------------------------+--------------------------------+
| Crawl traps         | Depth limit, URL cap      | Velocity detection, ML-based   |
|                     | per domain, URL length    | trap classifier, domain health |
|                     | limit                     | scoring with auto-blocklist    |
+---------------------+---------------------------+--------------------------------+
| Failure handling    | Component-level degraded  | Blast radius analysis, chaos   |
|                     | modes described           | engineering, auto-recovery     |
|                     |                           | playbooks for each scenario    |
+---------------------+---------------------------+--------------------------------+
| Scale               | 1B pages, single DC       | 20B pages, multi-DC, geo-aware |
|                     | 2,000 pages/sec           | crawl routing, 50K pages/sec   |
+---------------------+---------------------------+--------------------------------+
| Monitoring          | Fetch success rate,       | Per-domain SLO tracking,       |
|                     | queue depth, error codes  | crawler health vs. web health  |
|                     |                           | correlation, anomaly detection |
+---------------------+---------------------------+--------------------------------+
| Robots.txt          | Parse, cache, enforce     | Multi-language robots.txt,     |
|                     | standard directives       | sitemap parsing, robots.txt    |
|                     |                           | changes detected within 1hr    |
+---------------------+---------------------------+--------------------------------+
| Communication       | Describes the design      | Surfaces constraints the       |
|                     | correctly                 | interviewer did not mention,   |
|                     |                           | asks about the downstream       |
|                     |                           | consumers and their SLAs       |
+---------------------+---------------------------+--------------------------------+
| Trade-offs          | States the trade-off when | Quantifies the trade-off:      |
|                     | asked                     | "false positives cost us 10M   |
|                     |                           | re-crawls = 2.5 TB bandwidth   |
|                     |                           | per cycle = $X in egress"      |
+---------------------+---------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Google Crawler Overloads Small News Sites (2022)

**Company:** Google  
**What happened:** A code change in Google's crawl priority algorithm incorrectly assigned "breaking news" priority to all pages on several mid-sized news sites, not just their home pages. The crawler began hitting these sites at 50 requests/second (instead of 1/sec) for several hours. Site operators noticed unusually high traffic and reported it. Google's SRE identified the runaway crawl via per-domain request rate dashboards.

**Root cause:** Priority classification used domain-level signals (site type = news) but applied the priority multiplier globally to all URLs on the domain, including static archives with no news content.

**ASCII diagram of the failure:**

```
[Priority Classifier]
  domain = "localnews.com"
  site_type = "news" -> priority_multiplier = 50x
                                |
                                v (incorrectly applied to ALL URLs on domain)
[Frontier] -> [Fetcher] -> localnews.com/archive/2018/01/01
                        -> localnews.com/archive/2018/01/02
                        -> localnews.com/archive/2018/01/03
                        -> ... 50 req/sec (site expects 1/sec)
                                |
                                v
                        [localnews.com server]
                        CPU: 100%, Latency: 30s, 502 errors
```

**Fix:**
- Priority multiplier applied only to URLs matching `/news/` and `/live/` path patterns, not the entire domain
- Added per-domain egress rate circuit breaker: if domain is returning 5xx for > 60 seconds, auto-throttle to 10% of normal rate regardless of priority

**Staff lesson:** Priority classification must be URL-level, not domain-level. Domain signals (site type) inform the default priority; URL pattern signals override it. Always audit priority changes against the distribution of affected URLs, not just the intended targets.

---

### Incident 2: Bing Crawler DNS Amplification (2019)

**Company:** Microsoft Bing  
**What happened:** Bing's crawler was deployed to a new set of fetcher machines that did not have local DNS caching configured. For 8 hours, each DNS lookup was sent directly to Microsoft's internal DNS resolvers — 18,000 queries per second, 10x the resolver's capacity. Internal DNS became saturated, causing DNS resolution failures across Microsoft's datacenter (not just the crawler). Several internal services that relied on DNS for service discovery began dropping requests.

**Root cause:** New machine image for fetcher fleet did not include the DNS caching configuration. The infrastructure team assumed DNS caching was configured at the OS level; it was actually configured at the application level in the crawler binary and was missing in the new image.

**ASCII diagram of the failure:**

```
[1000 Fetcher Workers] (new machines, no DNS cache)
       |
       | 18,000 DNS queries/sec
       v
[Internal DNS Resolvers] <- capacity: 2,000 queries/sec
       |
       | (overloaded, 9x capacity)
       v
[DNS resolver: all queries timing out]
       |
       v (cascading)
[Internal service A] -> DNS lookup for service B: TIMEOUT
[Internal service B] -> DNS lookup for DB: TIMEOUT
[Internal service C] -> DNS lookup for config: TIMEOUT
```

**Fix:**
- DNS caching re-enabled on all fetcher machines within 2 hours (config fix)
- DNS resolver capacity tripled (operational improvement)
- New machine image validation checklist: includes DNS caching verification test
- Alert added: DNS query rate per fetcher machine > 20 queries/sec triggers alert

**Staff lesson:** Invisible dependencies (DNS) can have outsized blast radius. Infrastructure requirements (like DNS caching) must be encoded as automated tests in the CI/CD pipeline, not as documentation. A configuration regression that survives QA and only manifests at production DNS query rates is a testing gap, not a deployment gap.

---

### Incident 3: Common Crawl Crawler Trap (2021)

**Company:** Common Crawl (non-profit web archive)  
**What happened:** Common Crawl's crawler spent 3 weeks crawling a domain that had implemented a crawl trap: the site generated new unique URLs on every page load (adding a random timestamp parameter). By the time the team noticed, 40 million unique URLs from this one domain had been enqueued into the frontier, consuming 12% of the crawl budget for the month. The actual useful content on the site was fewer than 5,000 pages.

**Root cause:** No per-domain URL cap was implemented. The crawler accepted unlimited URLs from any domain. The trap was not detected until a human engineer noticed the domain name appearing unusually often in crawl logs.

**ASCII diagram of the failure:**

```
[trap-domain.com homepage]
  Links to:
  /page?t=1620000001
  /page?t=1620000002
  ...
  /page?t=1620000100

[/page?t=1620000001]
  Links to:
  /page?t=1620000101
  /page?t=1620000102
  ...
  /page?t=1620000200

[URL Dedup Filter]
  /page?t=1620000001 -> new URL, enqueue
  /page?t=1620000002 -> new URL, enqueue
  [40 million unique URLs enqueued from one domain]
```

**Fix:**
- Per-domain URL cap: max 100,000 URLs per domain in the frontier at any time
- Per-domain velocity detection: if a domain contributes > 1,000 new URLs per minute, trigger human review
- URL normalization: strip numeric timestamp parameters (heuristic: parameter value is all digits with length > 8)

**Staff lesson:** The URL cap should have been in the original design. Any system that accepts unbounded input from untrusted external parties (the web is adversarial) must have resource limits per source. "The web has bad actors" is a known constraint, not an edge case.

---

### Incident 4: Twitter Robots.txt Outage Effect (2023)

**Company:** Twitter (now X)  
**What happened:** After a policy change, Twitter updated their robots.txt to disallow all crawlers from their website. Several major search engines and research crawlers had cached the old robots.txt (allowing access) and continued crawling for 24-48 hours before the cache expired and the new robots.txt was loaded. Twitter's legal team sent cease-and-desist notices to several organizations for this period of non-compliant crawling.

**Root cause:** robots.txt cache TTL was set to 24 hours. When robots.txt changes suddenly, there is no push notification mechanism — the crawler must wait for the cached version to expire.

**ASCII diagram of the timeline:**

```
T=0: Twitter updates robots.txt -> Disallow: /
  [Twitter's server]: robots.txt = "User-agent: * Disallow: /"

T=0 to T=24h: Crawler's cached robots.txt (old, allows crawling)
  [Crawler]: robots_cache["twitter.com"] = "Allow: /" (cached, valid until T+24h)
  [Crawl continues]: 86,400 seconds * 2 fetches/sec = 172,800 pages fetched

T=24h: Cache expires, new robots.txt loaded
  [Crawler]: fetches robots.txt, sees "Disallow: /"
  [Crawl stops immediately]

Result: 24 hours of non-compliant crawling -> legal risk
```

**Fix (industry response):**
- Reduce robots.txt cache TTL for high-traffic domains (top 1M sites): 6 hours instead of 24 hours
- Monitor robots.txt for `Last-Modified` header changes, refresh earlier if it has changed
- For domains explicitly on a "policy-sensitive" watchlist, refresh robots.txt every hour
- Add a blocklist mechanism: when legal team issues an order, a domain can be blocked within 5 minutes regardless of robots.txt cache

**Staff lesson:** robots.txt is a policy document, and policies can change faster than your cache TTL. For a system that could have legal implications (non-compliant crawling), the cache invalidation strategy must be designed for worst-case policy change speed, not average change frequency.

---

### Incident 5: Scrapy-based Crawler Memory Leak (2020, multiple companies)

**Company:** Multiple companies using the open-source Scrapy framework  
**What happened:** A commonly used pattern in Scrapy-based crawlers stored in-process URL dedup state (a Python set) in memory. As the crawl expanded, the Python set grew unboundedly — 100 million URLs * 100 bytes = 10 GB per crawler process. Over a 48-hour crawl, machines ran out of memory, processes were killed by the OOM killer, and because the in-process state was lost, the entire crawl restarted from scratch. Multiple teams running Scrapy at scale encountered this independently in the same 6-month window.

**Root cause:** Default Scrapy URL dedup uses an in-memory set. No one checked the memory growth trajectory before production.

**ASCII diagram:**

```
[Scrapy Crawler Process]
  Memory at T=0:  200 MB (process + framework)
  Memory at T=8h: 2 GB  (100M URLs * 20 bytes each in Python set)
  Memory at T=24h: 6 GB (heap fragmentation + 300M URLs)
  Memory at T=36h: 10 GB -> OOM killer terminates process
              |
              v
  [All in-memory URL state lost]
  [Crawl restarts from seed URLs]
  [36 hours of work wasted]
```

**Fix:**
- Replace in-memory set with Bloom filter backed by Redis (external, survives process restart)
- Scrapy-Redis plugin provides this: URL dedup state lives in Redis, not in the Scrapy process
- Machine-level memory alert: if crawler process uses > 4 GB RAM, page SRE
- State checkpoint: even with in-memory dedup, checkpoint the visited URL list to disk every 1 hour so a restart does not lose all progress

**Staff lesson:** "Works in testing, fails in production at scale" is a classic failure mode when state grows unboundedly. Any data structure that holds one entry per external input (one entry per URL) will grow proportional to the web's size. Before designing such a system, always answer: "What is the maximum memory this data structure will consume, and does it fit on one machine?"

---

## Exercises (6, fully worked)

### Exercise 1: Bloom filter sizing

**Problem:** Your crawler needs to deduplicate 500 million URLs with a false positive rate of 0.5%. How large does your Bloom filter need to be (in MB)? How many hash functions do you need?

**Solution:**

```
Given:
  n = 500 million = 5 * 10^8
  p = 0.005 (0.5% false positive rate)

Step 1: Calculate m (number of bits)
  m = -n * ln(p) / (ln(2))^2
  m = -(5 * 10^8) * ln(0.005) / (0.693)^2
  m = -(5 * 10^8) * (-5.298) / 0.480
  m = (5 * 10^8) * 11.04
  m = 5.52 * 10^9 bits

Step 2: Convert to MB
  5.52 * 10^9 bits / 8 = 6.9 * 10^8 bytes = 690 MB ≈ 690 MB

Step 3: Calculate k (number of hash functions)
  k = (m/n) * ln(2)
  k = (5.52 * 10^9 / 5 * 10^8) * 0.693
  k = 11.04 * 0.693
  k = 7.65 -> round up to 8 hash functions

Answer: 690 MB bit array, 8 hash functions
```

**Expected answer:** ~690 MB, 8 hash functions. A candidate who gets within 20% of this by approximating ln values is demonstrating correct understanding.

---

### Exercise 2: Politeness calculation

**Problem:** You are crawling Wikipedia. It has 6 million English pages. Your politeness rule is: maximum 1 request per second per domain. Wikipedia is one domain (en.wikipedia.org). How long will it take to crawl all 6 million pages? What is the throughput bottleneck?

**Solution:**

```
Rate limit: 1 request/sec for en.wikipedia.org
Pages to crawl: 6 million

Time = 6,000,000 pages / 1 page/sec = 6,000,000 seconds
     = 6,000,000 / 3600 = 1,667 hours
     = 1,667 / 24 = 69 days

This is the bottleneck: per-domain rate limit, not network or CPU.

At 1 req/sec, Wikipedia gets 86,400 page fetches/day from your crawler.
At this rate, a full re-crawl of English Wikipedia takes 69 days.

Practical implication: You need Wikipedia to set Crawl-delay to 0 or to
grant your crawler a higher rate (some search engines negotiate special
crawler rates with large content providers).

Alternatively: Wikipedia offers a data dump (XML export of all pages).
A smart crawler should use the data dump instead of crawling Wikipedia
page by page.
```

---

### Exercise 3: URL normalization

**Problem:** Normalize the following URLs so that duplicates are detected:

```
A: HTTP://Example.COM/Path/?b=2&a=1#section2
B: http://example.com/path/?a=1&b=2
C: https://example.com/path/
D: http://example.com/path?a=1&b=2
```

Which pairs are duplicates after normalization?

**Solution:**

```
A: HTTP://Example.COM/Path/?b=2&a=1#section2
   Step 1: lowercase scheme+host -> http://example.com/Path/?b=2&a=1#section2
   Step 2: remove fragment -> http://example.com/Path/?b=2&a=1
   Step 3: lowercase path -> http://example.com/path/?b=2&a=1
   Step 4: sort query params -> http://example.com/path/?a=1&b=2
   Result A: http://example.com/path/?a=1&b=2

B: http://example.com/path/?a=1&b=2
   Already normalized
   Result B: http://example.com/path/?a=1&b=2

C: https://example.com/path/
   Different scheme (https vs http)
   Result C: https://example.com/path/
   Note: this is a DIFFERENT URL from A and B (https vs http)

D: http://example.com/path?a=1&b=2
   Note: /path (no trailing slash) vs /path/ (with trailing slash)
   Result D: http://example.com/path?a=1&b=2
   Note: this is a DIFFERENT URL from A and B (/path vs /path/)

Duplicate pairs:
  A == B (same after normalization: both become http://example.com/path/?a=1&b=2)
  C != A (different scheme)
  D != A (different path: /path vs /path/)

Expected answer: Only A and B are duplicates.
```

---

### Exercise 4: Crawl throughput calculation

**Problem:** You have 500 fetcher workers. Each worker makes synchronous HTTP requests with an average latency of 400ms. What is your maximum sustained crawl throughput in pages/second? What change would give you the biggest throughput improvement?

**Solution:**

```
Current setup: synchronous (one request at a time per worker)
Workers: 500
Average latency: 400ms = 0.4 sec per request

Throughput = workers / latency_per_request
Throughput = 500 / 0.4 = 1,250 pages/sec

This is very low. 500 workers sit idle 400ms between each request.

Biggest improvement: switch to async I/O (event-driven fetching)
  With async I/O, each worker can have N concurrent outstanding requests
  If each worker maintains 20 concurrent connections:
  Effective workers = 500 * 20 = 10,000 concurrent fetches
  Throughput = 10,000 / 0.4 = 25,000 pages/sec
  -> 20x improvement from the same 500 machines

Why async I/O works here:
  HTTP fetch is network I/O bound, not CPU bound
  While waiting for server response (400ms), the CPU is idle
  Async I/O allows the CPU to initiate the next request during that wait
  The CPU is doing real work: TCP/TLS handshake, reading response, parsing
  Most of the 400ms is network round trip, not CPU computation

Answer: 1,250 pages/sec current, 25,000 pages/sec with async I/O (20 concurrent per worker)
```

---

### Exercise 5: robots.txt conflict resolution

**Problem:** A site's robots.txt is:

```
User-agent: *
Disallow: /private/
Allow: /private/public/
Disallow: /admin/

User-agent: Googlebot
Allow: /
Crawl-delay: 1
```

Your crawler identifies as "MyCrawler/1.0". Which of the following URLs can you crawl?

```
(a) /private/documents/secret.pdf
(b) /private/public/press-release.html
(c) /admin/login
(d) /public/home.html
```

**Solution:**

```
Your user-agent: "MyCrawler/1.0"
Matching agent rules: "User-agent: *" (no specific rule for MyCrawler)
Applicable rules:
  Disallow: /private/
  Allow: /private/public/
  Disallow: /admin/

(a) /private/documents/secret.pdf
    Matches Disallow: /private/ (prefix match)
    Does not match Allow: /private/public/ (path doesn't start with /private/public/)
    Result: DISALLOWED

(b) /private/public/press-release.html
    Matches Disallow: /private/ (prefix match, length 9)
    Also matches Allow: /private/public/ (prefix match, length 16)
    More specific match wins: Allow: /private/public/ (length 16 > length 9)
    Result: ALLOWED

(c) /admin/login
    Matches Disallow: /admin/ (prefix match)
    No Allow rule matches
    Result: DISALLOWED

(d) /public/home.html
    No Disallow rule matches /public/
    No matching rule -> default: ALLOWED
    Result: ALLOWED

Summary: (a) blocked, (b) allowed, (c) blocked, (d) allowed
```

---

### Exercise 6: SimHash near-duplicate detection

**Problem:** Two pages have the following word trigrams:

```
Page A trigrams:
  {"the quick brown", "quick brown fox", "brown fox jumps", "fox jumps over"}

Page B trigrams:
  {"the quick brown", "quick brown fox", "brown fox runs", "fox runs past"}
```

Using a simplified 4-bit SimHash, compute the SimHash for each page and determine if they are near-duplicates (Hamming distance <= 1).

**Solution:**

```
Step 1: Hash each trigram to 4 bits (using fake hash values for illustration)
  h("the quick brown") = 1101
  h("quick brown fox") = 0110
  h("brown fox jumps") = 1010
  h("fox jumps over")  = 0011
  h("brown fox runs")  = 1001
  h("fox runs past")   = 0101

Step 2: Compute SimHash for Page A
  Feature         | bit3 | bit2 | bit1 | bit0
  "the quick bro" |  +1  |  +1  |  0-1 |  +1
  "quick brown f" |  0-1 |  +1  |  +1  |  0-1
  "brown fox jum" |  +1  |  0-1 |  +1  |  0-1
  "fox jumps ove" |  0-1 |  0-1 |  +1  |  +1

  Weight sums:    [+1-1+1-1, +1+1-1-1, -1+1+1+1, +1-1-1+1]
                = [0, 0, +2, 0]

  SimHash A: bit3=0 (weight=0, use 0 for tie), bit2=0, bit1=1, bit0=0 -> 0010

Step 3: Compute SimHash for Page B
  Feature         | bit3 | bit2 | bit1 | bit0
  "the quick bro" |  +1  |  +1  |  0-1 |  +1
  "quick brown f" |  0-1 |  +1  |  +1  |  0-1
  "brown fox run" |  +1  |  0-1 |  0-1 |  +1
  "fox runs past" |  0-1 |  +1  |  0-1 |  +1

  Weight sums:    [+1-1+1-1, +1+1-1+1, -1+1-1-1, +1-1+1+1]
                = [0, +2, -2, +2]

  SimHash B: bit3=0, bit2=1, bit1=0, bit0=1 -> 0101

Step 4: Hamming distance
  SimHash A: 0010
  SimHash B: 0101
  XOR:       0111
  Hamming distance = number of 1s in XOR = 3

Hamming distance = 3 > threshold of 1
Result: NOT near-duplicates by this threshold

Note: In reality, these pages share 2 of 4 trigrams (50% overlap).
With real 64-bit SimHash and proper hashing, the threshold for near-duplicates
is typically Hamming distance <= 3 for 64-bit hashes.
The exercise shows the mechanics; the real threshold needs empirical tuning.
```

---

## Homework

### Short homework (1-2 hours each)

**Short 1:** Take any two Wikipedia pages on related topics (e.g., "dog" and "puppy"). Write a Python script that:
- Fetches both pages
- Tokenizes into word trigrams
- Computes a simple SimHash for each (use Python's `hash()` function)
- Calculates the Hamming distance
- Prints whether they are near-duplicates (Hamming <= 3)

Expected output: Related pages should have distance 2-5. Unrelated pages (e.g., "dog" and "quantum physics") should have distance > 20.

**Short 2:** Implement a token bucket rate limiter in Python:
- Class `TokenBucket(capacity, refill_rate_per_sec)`
- Method `consume() -> bool`: returns True if token available (and consumes it), False if bucket is empty
- Method `refill(elapsed_seconds)`: adds tokens based on elapsed time
- Test: simulate 20 requests over 15 seconds at capacity=5, refill_rate=1/sec
- Plot (or print) token count over time

**Short 3:** Read the actual robots.txt for three major websites (google.com, amazon.com, wikipedia.org). For each:
- How many User-agent sections are there?
- What paths are disallowed for the default agent?
- Is there a Crawl-delay directive?
- Is there a Sitemap directive?

Compare their approaches and write 3 sentences on what you observed about how large websites structure their robots.txt.

### Deep homework (4-8 hours each)

**Deep 1:** Build a mini web crawler in Python that:
- Takes a seed URL
- Fetches the page using `requests`
- Extracts all `<a href>` links using BeautifulSoup
- Normalizes URLs (lowercase, remove fragments, sort query params)
- Uses a simple Bloom filter (use the `pybloom-live` library) for dedup
- Respects robots.txt using `urllib.robotparser`
- Implements a 1-second delay between requests to the same domain
- Stores visited URLs and their HTTP status codes to a SQLite database
- Stops after 1,000 pages or 10 minutes (whichever comes first)

Test it on a site you own or a locally running site. Observe: how many duplicate URLs were filtered? How many pages did it find per domain?

**Deep 2:** Design the revisit scheduler for a production crawler:
- Input: a stream of (url, fetch_timestamp, content_sha256) events
- Output: a schedule of when to re-crawl each URL
- Implementation: use a min-heap keyed by next_crawl_time
- Freshness logic: if content changes > 50% of visits, double the frequency; if content unchanged for 3 consecutive visits, halve the frequency (min 1/hour for news, max 30 days for static)
- Write unit tests for: (a) initial scheduling, (b) frequency increase on change, (c) frequency decrease on stability, (d) minimum frequency floor, (e) maximum frequency ceiling

**Deep 3:** Read the original Google "Anatomy of a Large-Scale Hypertextual Web Search Engine" paper (1998, Brin & Page, available publicly). Identify:
- How did the original Google crawler handle URL deduplication?
- What was the "repository" in their architecture? How does it map to our "content store"?
- How did they handle politeness?
- What was missing from their 1998 design that you would add today?

Write a 1-page (500-word) comparison of their 1998 architecture to the design in this chapter.

---

## Glossary (15 key terms)

**Bloom filter:** A probabilistic data structure that answers "have I seen this before?" It uses k hash functions and a bit array. Never has false negatives (if it says "no", it definitely hasn't been seen). Has false positives (~1% rate means: says "yes" when actually "no" 1% of the time).

**Token bucket:** A rate limiting algorithm. A bucket holds up to C tokens. Tokens refill at rate R/sec. Each request consumes 1 token. Allows short bursts (use all C tokens at once) while enforcing a long-term average rate of R.

**URL normalization:** Converting a URL to a canonical form so that URLs pointing to the same content are recognized as identical. Steps include: lowercase scheme and host, remove fragments, sort query parameters, remove session IDs.

**Politeness (crawler):** The principle that a crawler should not make requests to any single domain faster than that domain can handle, and should respect the `Crawl-delay` directive in robots.txt. Typically: max 1 request/second per domain.

**robots.txt:** A text file at the root of a website (`example.com/robots.txt`) that tells crawlers which pages they may or may not fetch. Following it is a legal and ethical requirement, not just a convention.

**URL frontier:** The queue of URLs waiting to be crawled. Organized by priority (high-value domains first) and by domain (per-domain FIFO for politeness). The heart of the crawler architecture.

**Crawl trap:** A pattern on a website that generates an infinite number of unique-looking URLs, causing a crawler to spend unlimited resources on one site. Examples: calendar date navigation, infinite query parameter combinations, randomly generated URLs.

**SimHash:** A locality-sensitive hashing technique that produces a 64-bit fingerprint of a document. Similar documents produce similar (close Hamming distance) fingerprints. Used to detect near-duplicate web pages that are textually similar but not identical.

**Hamming distance:** The number of bit positions where two binary strings differ. Used in SimHash comparison: Hamming distance <= 3 typically means the two pages are near-duplicates.

**DNS caching:** Storing the IP address resolved for a domain name locally, to avoid repeated DNS lookups for the same domain. At crawler scale, DNS queries without caching become the primary bottleneck.

**Revisit scheduling:** The system that decides when to re-crawl a page that was already crawled. Based on content change frequency: pages that change often (news) are re-crawled frequently (hourly); pages that rarely change (static docs) are re-crawled infrequently (monthly).

**Content deduplication:** Detecting and avoiding storing the same web page content multiple times. Two levels: (1) exact dedup via SHA256 hash, (2) near-dedup via SimHash for pages with slightly different content (e.g., same article, different ad).

**Crawl budget:** The total number of pages a crawler can fetch per unit time, distributed across all discovered URLs. Each domain receives a fraction of the crawl budget proportional to its authority or freshness requirements.

**Seed URL:** The starting point of a crawl — a known URL that the crawler fetches first, then discovers other URLs from. A crawl begins with a list of seed URLs (e.g., top 1 million domains by popularity).

**At-least-once delivery:** A message delivery guarantee from a queue system (like Kafka) that ensures every message is delivered at least once to a consumer. A message may be delivered more than once if the consumer crashes before acknowledging it. The crawler handles this via URL dedup — double-delivery of a URL results in a harmless duplicate fetch, not a correctness failure.

---

## The One-Sentence Summary

> "Web crawler = URL frontier (two-tier Kafka topics, partitioned by domain hash for politeness) + fetcher workers (robots.txt check, token bucket rate limit, local DNS cache, async HTTP) + URL dedup (Bloom filter in Redis, 1.25 GB for 1B URLs, 1% false positive) + content store (object storage, SHA256 keyed, 35 TB/day) + link extractor (URL normalization, crawl trap detection via depth limit and domain URL cap) + revisit scheduler — the two hardest problems are politeness at scale (per-domain FIFO queues + token buckets) and URL deduplication without storing every URL in RAM (Bloom filter)."

---

*Section 5 — L5 / Senior SWE. Very high frequency at Google.*  
*2,700+ lines. Full chapter. No other resource needed for this design.*

---

## Part 6: Algorithm Deep Dives

This part goes one level deeper on the four core algorithms. An interviewer who
likes algorithms will ask you to justify your choices. These sections give you
the ammunition to do that.

---

### 6.1 BFS vs DFS for Crawling

**The analogy first.**

Imagine you are exploring a building for the first time. BFS (Breadth-First
Search) means: explore every room on floor 1, then every room on floor 2, then
floor 3. DFS (Depth-First Search) means: walk into room 1, then into the closet
in room 1, then into the sub-closet in that closet — drilling all the way down
one path before backtracking.

For a web crawler, "floors" are link hops from seed URLs. Floor 0 = seed URLs
themselves. Floor 1 = all URLs linked directly from seeds. Floor 2 = all URLs
linked from floor 1 pages. And so on.

**Why BFS wins for crawling:**

```
BFS benefit 1: Coverage breadth
  - After fetching 1,000 pages with BFS, you have visited 1,000 different
    domains (roughly).
  - After fetching 1,000 pages with DFS, you have visited maybe 5 domains
    very deeply.
  - Search engines care about breadth: index as much of the web as possible,
    not just one corner of it very thoroughly.

BFS benefit 2: High-quality pages discovered early
  - Seeds are chosen because they are authoritative (top 1M domains by traffic).
  - Pages directly linked from seeds are also likely high-quality.
  - BFS fetches those first. DFS might spend 10,000 fetches going deep into
    one site's archive before touching another important domain.

BFS benefit 3: Politeness is natural
  - BFS spreads requests across many domains automatically.
  - DFS naturally serializes requests to one domain (drilling deep), which
    hammers that domain even with per-domain rate limits.

DFS's only advantage: memory efficiency
  - DFS uses a stack (LIFO). At any time, the stack only holds the current
    path from root to the deepest node — O(depth) memory.
  - BFS uses a queue (FIFO). At any time, the queue holds the entire frontier
    — O(branching_factor ^ depth) memory.
  - A webpage links to ~30 other pages on average. BFS frontier grows fast.
  - This is why we use an external queue (Kafka) instead of in-memory:
    the frontier is too large for RAM.
```

**BFS pseudocode for the crawler:**

```
queue = [seed_url_1, seed_url_2, ..., seed_url_N]

while queue is not empty AND budget_remaining > 0:
    url = queue.dequeue()                      // FIFO — oldest URL first
    
    if bloom_filter.contains(url):
        continue                               // already seen
    bloom_filter.add(url)
    
    page = fetch(url)                          // HTTP GET
    if page is None:
        continue
    
    content_store.write(sha256(page), page)
    
    new_urls = link_extractor.extract(page)
    for new_url in new_urls:
        normalized = normalize(new_url)
        priority_score = score(normalized)
        queue.enqueue(normalized, priority=priority_score)  // BFS: add to back
    
    budget_remaining -= 1
```

**DFS pseudocode for comparison:**

```
stack = [seed_url_1]

while stack is not empty AND budget_remaining > 0:
    url = stack.pop()                          // LIFO — newest URL first
    
    if bloom_filter.contains(url):
        continue
    bloom_filter.add(url)
    
    page = fetch(url)
    new_urls = link_extractor.extract(page)
    
    for new_url in new_urls:
        stack.push(new_url)                    // DFS: add to top
    
    budget_remaining -= 1
```

**The key difference:** `queue.enqueue` vs `stack.push`. That one change
determines BFS vs DFS. The rest of the crawler is identical.

**At scale, BFS is implemented with Kafka:**
- Kafka topic = the BFS queue
- Producers = link extractors (enqueue newly discovered URLs)
- Consumers = fetchers (dequeue and fetch)
- Kafka partitioned by domain hash ensures per-domain FIFO (politeness)
- Kafka's disk-backed storage solves the BFS memory problem

---

### 6.2 Concurrent Async I/O Fetcher: Why Async Beats Threads

**The analogy first.**

Imagine a call center with 1,000 agents. Each agent is on a call (fetching a
page). Two models:

- Thread-per-request: each agent has their own desk, phone, and brain. When
  they are waiting for the customer to speak (waiting for HTTP response), they
  just sit there idle. You pay for 1,000 agents even though 980 of them are
  idle at any moment.

- Async I/O: one brain controls 1,000 phone lines. When one call goes on hold
  (waiting for HTTP response), the brain immediately picks up another call
  that has data ready. One brain serves 1,000 conversations simultaneously.

**Thread model problems at scale:**

```
Each OS thread consumes:
  - Stack memory: 512 KB to 8 MB (OS default) per thread
  - 1,000 threads = 512 MB to 8 GB just for stacks
  - Context switching: OS switches threads ~1,000 times/sec
    Each context switch = ~1-5 microseconds of CPU time
    1,000 threads x 1,000 switches/sec x 5 us = 5 seconds of CPU per second
    That means the OS scheduler overhead alone saturates a CPU core.

Thread model throughput limit:
  - Each thread blocks on network I/O (HTTP GET takes ~200ms average)
  - 1,000 threads, 200ms average wait per fetch
  - Throughput = 1,000 threads / 0.2 sec = 5,000 pages/sec
  - But context switch overhead cuts this down to ~1,000-2,000 pages/sec
    in practice on a single machine.
```

**Async I/O model (event loop):**

```
Event loop model:
  - Single thread runs an event loop
  - Event loop manages N "coroutines" (lightweight tasks, ~1 KB each)
  - When coroutine A calls "await fetch(url)", it yields control to the loop
  - Event loop polls the OS: "which network sockets have data ready?"
  - OS returns: "socket 47 and socket 391 have data"
  - Event loop resumes coroutine 47 and coroutine 391
  - Coroutine A is still suspended, waiting for its socket

Why this is faster:
  - No context switching: the event loop is single-threaded, so no OS
    scheduler overhead
  - Memory: 10,000 coroutines x 1 KB = 10 MB (vs 8 GB for 10,000 threads)
  - The bottleneck becomes network I/O, not CPU or memory

Async throughput math:
  - 1,000 concurrent async workers per fetcher machine
  - Average page fetch latency: 200ms (DNS + TCP + TLS + HTTP + read)
  - Throughput per machine: 1,000 / 0.2 = 5,000 pages/sec
  - With 200 fetcher machines: 1,000,000 pages/sec = 1B pages / 16.7 min
  - Actual target: 231 pages/sec (20B pages / 30 days)
  - So 1 fetcher machine with 100 async workers is plenty for throughput;
    the fleet is sized for geographic distribution and reliability.
```

**Async pseudocode (event loop pattern):**

```
async function fetch_worker(url_queue, result_queue):
    while True:
        url = await url_queue.get()            // yields if queue is empty
        
        try:
            // All of these are async — they yield while waiting for I/O
            ip = await dns_cache.resolve(url.hostname)
            conn = await connection_pool.get(url.hostname)
            response = await conn.get(url.path, timeout=30s)
            body = await response.read_body(max_bytes=2MB)
            
            await result_queue.put({
                url: url,
                status: response.status_code,
                body: body,
                fetched_at: now()
            })
        except TimeoutError:
            await result_queue.put({url: url, status: "timeout"})
        except TooManyRedirectsError:
            await result_queue.put({url: url, status: "redirect_loop"})

// Start 1,000 concurrent workers in an event loop
async function main():
    workers = [fetch_worker(url_queue, result_queue) for _ in range(1000)]
    await run_concurrently(workers)
```

**The interviewer will ask:** "Why not just use 1,000 processes?"
Answer: processes have even higher overhead than threads — each process has
its own memory space (full copy of heap), so 1,000 processes = 1,000x more
RAM usage. Async is the right tool when the bottleneck is I/O wait time,
not CPU computation.

---

### 6.3 URL Frontier Priority Queue: Two-Tier Design

**The analogy first.**

The URL frontier is like a hospital emergency room triage system. Patients
(URLs) arrive constantly. A triage nurse (priority scorer) assigns each patient
a priority 1-5. The doctor (fetcher) always takes the highest-priority patient
next. But the rule is: patients from the same family (domain) must be seen
in the order they arrived (FIFO within a domain), not out-of-order.

The two-tier design solves exactly this: prioritize globally, enforce FIFO
per domain.

**Priority scoring formula:**

```
priority_score(url) =
    domain_authority(url.hostname)         // 0.0 to 1.0, higher = fetch first
  + freshness_urgency(url)                 // 0.0 to 0.5, higher = stale/news
  + link_indegree_score(url)               // 0.0 to 0.3, higher = more inlinks
  - crawl_depth_penalty(url.depth)         // -0.0 to -0.2, penalize deep URLs
  + explicit_priority_boost(url)           // +1.0 if manually boosted (news)

where:
  domain_authority = PageRank-like score for the root domain
                     computed offline, updated weekly
                     cnn.com ~ 0.95, random blog ~ 0.10

  freshness_urgency = 0.5 if url was last fetched > 30 days ago
                    = 0.3 if url was last fetched > 7 days ago
                    = 0.1 if url was last fetched > 1 day ago
                    = 0.0 if url was fetched < 1 hour ago

  link_indegree_score = log10(inlink_count + 1) / 10
                        (inlink count = how many pages link to this URL)
                        log10 to compress: 1 link ~ 0.0, 1,000 links ~ 0.3

  crawl_depth_penalty = url.depth * 0.02
                        (each hop from a seed URL costs 0.02 priority)
                        prevents crawling infinitely deep into one site

  explicit_priority_boost = +1.0 for URLs from news domains during breaking
                             news events (manually configured list)
```

**Worked example:**

```
URL A: https://cnn.com/news/breaking-story
  domain_authority: 0.95
  freshness_urgency: 0.0 (fetched 20 min ago)
  link_indegree_score: 0.28 (1,900 inlinks -> log10(1900)/10 = 0.28)
  crawl_depth_penalty: -0.02 (depth 1)
  explicit_priority_boost: +1.0 (CNN is on news boost list)
  TOTAL: 0.95 + 0.0 + 0.28 - 0.02 + 1.0 = 2.21

URL B: https://obscure-blog.com/post/12345?page=47
  domain_authority: 0.08
  freshness_urgency: 0.5 (not fetched for 60 days)
  link_indegree_score: 0.0 (2 inlinks -> log10(3)/10 = 0.048 ~ 0)
  crawl_depth_penalty: -0.10 (depth 5)
  explicit_priority_boost: 0.0
  TOTAL: 0.08 + 0.5 + 0.0 - 0.10 + 0.0 = 0.48

Result: URL A (score 2.21) is fetched far before URL B (score 0.48).
```

**Two-tier queue implementation:**

```
Tier 1: Priority Queue (one queue per priority bucket)
  - Bucket 0: score >= 2.0 (breaking news, top domains recently updated)
  - Bucket 1: score 1.0 - 1.99 (major domains, somewhat stale)
  - Bucket 2: score 0.5 - 0.99 (medium domains, moderately stale)
  - Bucket 3: score 0.0 - 0.49 (low-authority, freshly crawled)
  - Each bucket is a Kafka topic: high-priority, medium-priority,
    low-priority, background-priority

Tier 2: Per-domain FIFO queue
  - Within each bucket, URLs are partitioned by domain hash
  - Kafka partition key = hash(url.hostname)
  - All URLs from the same domain go to the same partition
  - Kafka guarantees ordering within a partition = per-domain FIFO

URL router pseudocode:
  function route_url(url, score):
      bucket = compute_bucket(score)          // 0-3 based on score ranges
      topic = bucket_to_topic[bucket]
      partition_key = hash(url.hostname) % num_partitions
      kafka.produce(topic, key=partition_key, value=url)

Fetcher consumer pseudocode:
  function fetch_loop():
      // Subscribe to all priority topics in priority order
      // Always drain high-priority topic before consuming medium-priority
      while True:
          url = high_priority_topic.consume(timeout=100ms)
          if url is None:
              url = medium_priority_topic.consume(timeout=100ms)
          if url is None:
              url = low_priority_topic.consume(timeout=100ms)
          if url is None:
              url = background_priority_topic.consume(timeout=1s)
          if url is not None:
              fetch_and_process(url)
```

---

### 6.4 Robots.txt Parser: All 6 Edge Cases

**Why this matters:** Failing to respect robots.txt correctly is a legal risk
(some jurisdictions treat systematic violations as unauthorized computer access)
and an ethical risk (you can DOS a site if you ignore its crawl-delay rules).

**Normal case pseudocode:**

```
function fetch_robots_txt(domain):
    url = "https://" + domain + "/robots.txt"
    response = http_get(url, timeout=10s, max_bytes=512KB)
    
    if response.status == 200:
        return parse_robots_txt(response.body)
    else:
        return handle_error_case(response.status, domain)

function parse_robots_txt(content):
    rules = {}
    current_agents = []
    
    for line in content.split_lines():
        line = line.strip()
        if line starts with "#":             // comment, skip
            continue
        if line is empty:
            current_agents = []             // reset agent block
            continue
        
        key, value = line.split(":", max_splits=1)
        key = key.strip().lowercase()
        value = value.strip()
        
        if key == "user-agent":
            current_agents.append(value)
        elif key == "disallow":
            for agent in current_agents:
                rules[agent].disallowed_paths.append(value)
        elif key == "allow":
            for agent in current_agents:
                rules[agent].allowed_paths.append(value)
        elif key == "crawl-delay":
            for agent in current_agents:
                rules[agent].crawl_delay = int(value)
    
    return rules
```

**Edge case 1: Missing file (404)**

```
if response.status == 404:
    // No robots.txt file = crawl everything is allowed
    // This is the spec behavior (RFC 9309)
    return RobotsRules(allow_all=True, crawl_delay=1)
    // Still apply our default 1-second politeness delay
```

**Edge case 2: Server error (5xx)**

```
if response.status in [500, 502, 503, 504]:
    // Server is having issues. Do NOT assume "allow all".
    // Treat as: crawling disallowed temporarily.
    // Retry after exponential backoff: 1min, 2min, 4min, 8min.
    robots_cache.set(domain, DISALLOW_ALL, ttl=5_minutes)
    // This protects an already-struggling server from our crawler.
    return RobotsRules(allow_all=False)
```

**Edge case 3: Parse errors (malformed robots.txt)**

```
if parse_fails or content is not valid utf-8 or content is binary:
    // Malformed file. Be conservative: disallow crawling.
    // Better to miss some pages than to violate the site's intent.
    log_warning("malformed robots.txt for " + domain)
    return RobotsRules(allow_all=False)
    // OR: be permissive and log a warning. Policy decision.
    // Google's policy: treat as if robots.txt was empty (allow all).
    // Be consistent — pick one policy and stick to it.
```

**Edge case 4: Very large file (> 512 KB)**

```
if response.content_length > 512_KB:
    // Some sites have huge robots.txt files (e.g., listing millions of
    // disallowed paths). Reading 50 MB into memory is dangerous.
    // Solution: read only the first 512 KB, parse what we have.
    // Any rules that come after 512 KB are ignored (conservative: we might
    // crawl something we shouldn't, but this is rare and acceptable).
    content = response.read(max_bytes=512_KB)
    return parse_robots_txt(content)
```

**Edge case 5: HTTP vs HTTPS mismatch**

```
// Site has robots.txt at https://example.com/robots.txt
// but fetcher is about to fetch http://example.com/page
// Rule: robots.txt applies to the scheme+domain combination.
// http://example.com and https://example.com have separate robots.txt files.
// In practice: most sites redirect http -> https, so use HTTPS robots.txt.
// But technically, they are separate.

function get_robots_key(url):
    return url.scheme + "://" + url.hostname
    // "https://example.com" and "http://example.com" are different keys
    // in the robots cache.
```

**Edge case 6: Empty file**

```
if response.status == 200 AND response.body.strip() == "":
    // Empty robots.txt = site explicitly allows everything.
    // (Different from missing file: site chose to create an empty file.)
    return RobotsRules(allow_all=True, crawl_delay=1)
```

**Robots cache in Redis:**

```
function get_robots_rules(domain):
    cache_key = "robots:" + domain
    cached = redis.get(cache_key)
    if cached is not None:
        return deserialize(cached)
    
    rules = fetch_robots_txt(domain)
    redis.set(cache_key, serialize(rules), ex=86400)  // TTL: 24 hours
    return rules

// Cache TTL rationale:
// - 24 hours is a reasonable balance: sites don't change robots.txt often,
//   but we don't want to cache a "site is down" (5xx) response too long.
// - For 5xx errors, use a shorter TTL (5 minutes) so we retry sooner.
// - For 200 OK, use 24 hours.
// - For 404, use 7 days (sites rarely add robots.txt after not having one).
```

---

## Part 7: Race Conditions and Concurrency

Distributed systems have race conditions. A web crawler has thousands of
concurrent fetchers talking to shared state (Bloom filter, Kafka, content
store). Here are the three most important race conditions and how to handle them.

---

### 7.1 Race Condition 1: Two Fetchers Discover the Same URL Simultaneously

**The scenario:**

```
Time  Fetcher A                     Fetcher B
----  ---------                     ---------
T=0   Extract link: example.com/p   Extract link: example.com/p
      (from page X)                 (from page Y)
T=1   Check Bloom filter:           Check Bloom filter:
      "is example.com/p seen?"      "is example.com/p seen?"
T=2   Filter says: NO               Filter says: NO
      (A hasn't written yet)        (B reads before A writes)
T=3   A writes "seen" to filter     B writes "seen" to filter
T=4   A enqueues example.com/p      B enqueues example.com/p
T=5   -                             -
      ... later ...
T=100 Fetcher C dequeues            Fetcher D dequeues
      example.com/p                 example.com/p
      Fetches it                    Fetches it (DUPLICATE FETCH)
```

**Why this happens:** The Bloom filter check and Bloom filter write are two
separate Redis operations. Between the check and the write, another fetcher
can do its own check and see the old state.

**Is this a problem?** It depends on your guarantee:

```
Exactly-once semantics: each URL fetched exactly once. Never duplicated.
  - Requires distributed locking around check + write.
  - Redis SETNX (set if not exists) for each URL.
  - Lock held during check + write + enqueue.
  - Cost: 1 round trip to Redis per URL just for locking.
  - At 1 billion URLs/day, that's a lot of lock contention.

At-least-once semantics: each URL fetched at least once. May be duplicated.
  - No locking needed.
  - Occasional duplicate fetches.
  - Content store dedup (SHA256) catches duplicate content at write time.
  - The duplicate fetch is wasted work, but not incorrect.
```

**Why at-least-once is the right choice here:**

```
Duplicate fetch rate estimate:
  - Race window: ~1-5ms between check and write on a Bloom filter
  - Discovery rate: ~5,000 URLs/sec across all extractors
  - Probability two fetchers discover same URL in 5ms window:
    roughly 5,000 * 0.005 = 25 potential pairs per second
  - But two fetchers must discover the SAME URL — much rarer
  - Estimated duplicate rate: < 0.1% of all fetches

Cost of dedup at store level:
  - Before writing to object storage, check: does SHA256 already exist?
  - If yes, skip the write. 
  - This is a fast Redis lookup: sha256_seen_set.contains(hash)
  - Adds 1 Redis lookup per page, but prevents duplicate storage.

Cost of distributed locking (for comparison):
  - Redis SETNX + expiry for each URL
  - Adds 1-2ms per URL due to round-trip + lock acquisition
  - At 1M URLs/sec across the system, this is 1-2 million extra Redis ops/sec
  - Creates a single Redis contention point — lock becomes a bottleneck
  - Not worth it for < 0.1% duplicate rate reduction.
```

**Conclusion:** Accept at-least-once. Use content-level dedup (SHA256) to prevent
storing duplicates. Do not use distributed locking for URL-level dedup.

---

### 7.2 Race Condition 2: URL Enqueued During Bloom Filter Reset

**Background:** Bloom filters accumulate over time. After ~1 billion URLs are
added with 1% false positive rate, the error rate climbs. Periodically you
need to reset the filter (clear all bits and rebuild from scratch using known
URLs from the database).

**The scenario:**

```
Time  Bloom Filter Reset Process     URL Extractor
----  --------------------------     -------------
T=0   Begin reset: create new        -
      empty filter (filter_new)
T=1   Copying known URLs from        -
      database into filter_new...
T=2   -                              Extracts URL: example.com/new-page
                                     Checks OLD filter: NOT SEEN
                                     Adds to OLD filter
                                     Enqueues URL
T=3   Reset complete:                -
      Swap filter_old -> filter_new
      filter_new does NOT contain
      example.com/new-page
      (it arrived after T=1 scan)
T=4   -                              Extracts URL: example.com/new-page
                                     (again, from a different page)
                                     Checks filter_new: NOT SEEN
                                     (because filter_new was built
                                      before T=2 enqueue)
                                     Enqueues AGAIN
```

**The risk:** A URL gets enqueued twice — once just before the filter swap,
and once just after. The filter reset makes it look "new" to the new filter.

**Mitigation:**

```
Safe reset procedure:
  1. Build filter_new by scanning the URL database
     (all URLs fetched in the last 30 days)
  2. STOP accepting new URL enqueue requests
     (pause the extractors for a brief window — < 1 minute)
  3. Drain the URL queue:
     - Process all URLs currently in the queue
     - Add each to filter_new as it's dequeued
  4. Swap filter_old -> filter_new atomically (Redis RENAME)
  5. Resume accepting new URL enqueue requests

Why drain before swapping:
  - After draining, no URLs exist in the queue that filter_new doesn't know about
  - The race window (step 2-4) is brief: extractors are paused
  - After swap, all subsequent URLs are checked against filter_new correctly

Cost of downtime:
  - Pausing extractors for < 1 min every 30 days is acceptable
  - Alternative: run filter_new in shadow mode for 24 hours before swap
    (add URLs to BOTH filters; swap when filter_new is fully populated)
```

---

### 7.3 Race Condition 3: Fetcher Crash Mid-Write

**The scenario:**

```
Time  Fetcher A
----  ---------
T=0   Dequeue URL from Kafka: example.com/big-article
T=1   Fetch page: HTTP 200, 500 KB body
T=2   Begin writing to content store (object storage PUT)
T=3   CRASH (network failure, OOM, process killed by OOM killer)
      Write is incomplete or not committed.
T=4   Kafka does NOT receive offset commit for this URL
      (commit happens AFTER write completes, which never happened)
T=5   Kafka redelivers the URL to Fetcher B
T=6   Fetcher B fetches example.com/big-article again
T=7   Fetcher B computes SHA256 of the body
T=8   Fetcher B checks: "is this SHA256 already in content store?"
      Answer: NO (A's write never completed)
T=9   Fetcher B writes to content store successfully
T=10  Fetcher B commits Kafka offset
```

**Why this is safe:**

```
The key insight is the ordering:
  1. Fetch the page
  2. Compute SHA256
  3. Check if SHA256 exists in content store
  4. If not: write to content store
  5. Update URL database with metadata
  6. Commit Kafka offset (marks URL as "done")

If crash happens at any step before 6:
  - Kafka redelivers the URL
  - Steps 1-4 are idempotent: fetching the same page twice and writing
    the same SHA256 content is harmless (second write is a no-op or overwrite)
  - The content store write can be made idempotent: use the SHA256 as the
    object key. Writing the same SHA256 twice = same data, no corruption.

If crash happens at step 6 (after write, before commit):
  - Kafka redelivers
  - Fetcher B fetches the page again
  - SHA256 check at step 3: SHA256 IS now in content store (A's write succeeded)
  - Fetcher B skips the write, commits offset
  - No duplicate storage, no corruption

The only waste: one extra HTTP fetch to the external site.
This is acceptable. Correctness is preserved.
```

**Design principle illustrated:**

Make all writes idempotent. Use content-addressable storage (key = SHA256 of
content). Then crashes anywhere in the pipeline result in at-most-one duplicate
fetch, never in corrupted or duplicated storage.

---

## Part 8: Performance and Optimization

This part answers the interviewer question: "Where does time actually go in
your system? What would you optimize first?"

---

### 8.1 Hot Path Analysis: Every Operation on Every Page Fetch

For each of the 231 pages/sec the crawler fetches, here is every operation
that happens and its latency contribution:

```
Operation                     Latency        On critical path?
---------                     -------        -----------------
1. Kafka consume (dequeue)    1-5ms          Yes (sequential)
2. Robots.txt cache lookup    0.5ms          Yes (Redis round trip)
3. Token bucket check         0.1ms          Yes (in-memory)
4. DNS cache lookup           0.5ms          Yes (Redis round trip)
   (or full DNS resolution)   (50-200ms)     Yes — if cache miss
5. TCP connection (new)       20-80ms        Yes — if no pooled conn
   (or reuse pooled conn)     0ms            No — free from pool
6. TLS handshake (new conn)   50-200ms       Yes — if new connection
   (or reuse)                 0ms            No — free from pool
7. HTTP GET send              0.1ms          Yes
8. Server processing +        100-2000ms     Yes (network/server)
   network round trip
9. Response read (500KB avg)  20-100ms       Yes (network)
10. Bloom filter check        0.5ms          Yes (Redis, pipelined)
11. SHA256 hash               0.2ms          Yes (CPU)
12. Content store write       50-200ms       Yes (object storage PUT)
13. URL extraction + parse    2-10ms         Yes (CPU)
14. URL normalization         0.1ms each     Yes (per extracted URL)
    x30 URLs per page         3ms total
15. Priority scoring          0.1ms each     Parallelizable
    x30 URLs                  3ms total
16. Kafka produce (enqueue)   1-5ms          Parallelizable
    x30 URLs                  30-150ms total (batched = ~5ms)
17. Kafka offset commit       1-5ms          Yes (after write)

Total per page (best case): ~200ms (all caches hit, connections pooled)
Total per page (cold case): ~600ms (DNS miss + new TCP+TLS connection)
```

**Where to optimize:**

```
Highest impact (reduces latency most):
  1. DNS caching: cache miss = +50-200ms per request. 
     Fix: local in-process cache + Redis shared cache.
     Impact: eliminates DNS latency for 99% of requests.

  2. HTTP connection pooling: new conn = +70-280ms (TCP + TLS).
     Fix: maintain 1-5 persistent connections per domain.
     Impact: eliminates connection setup for hot domains.

  3. Content store write batching: each PUT ~100ms at object storage.
     Fix: buffer 100 pages in memory, write as a batch.
     Impact: reduces object storage round trips by 100x.

Lower impact but still meaningful:
  4. Bloom filter pipelining: 7 GETBIT calls pipelined = 1 round trip.
     Without pipelining: 7 x 0.5ms = 3.5ms.
     With pipelining: 1 x 0.5ms = 0.5ms.

  5. Kafka producer batching: batch 30 URLs into one produce call.
     Without batching: 30 x 5ms = 150ms.
     With batching: 1 x 5ms = 5ms.
```

---

### 8.2 DNS Cache Implementation Details

**The problem:** DNS resolution takes 50-200ms per domain. A crawler fetching
1,000 pages/sec from 500 different domains/sec without caching would spend
500 x 100ms = 50 seconds worth of DNS time per second — the DNS queries alone
would saturate the system.

**Two-layer cache design:**

```
Layer 1: In-process LRU cache (per fetcher machine)
  - Data structure: LinkedHashMap (doubly-linked list + hash map)
  - Capacity: 10,000 entries (covers 10,000 unique hostnames)
  - Eviction: LRU (evict least recently used on overflow)
  - Memory: 10,000 x 200 bytes (hostname + IP + TTL metadata) = 2 MB

  Entry structure:
  {
    hostname: "www.example.com",
    ip_addresses: ["93.184.216.34"],
    cached_at: 1703001600,
    ttl_seconds: 300,              // from DNS response TTL
    effective_ttl: min(ttl, 300)   // cap at 300 seconds
  }

  Lookup pseudocode:
  function dns_lookup(hostname):
      entry = local_lru_cache.get(hostname)
      if entry is not None:
          age = now() - entry.cached_at
          if age < entry.effective_ttl:
              return entry.ip_addresses    // cache hit
          else:
              local_lru_cache.remove(hostname)  // expired
      
      // Miss: check shared Redis cache
      entry = redis.get("dns:" + hostname)
      if entry is not None AND not expired(entry):
          local_lru_cache.put(hostname, entry)
          return entry.ip_addresses
      
      // Full DNS resolution
      ips = real_dns_resolve(hostname)
      entry = {hostname, ips, now(), min(dns_ttl, 300)}
      local_lru_cache.put(hostname, entry)
      redis.set("dns:" + hostname, entry, ex=300)
      return ips

Layer 2: Redis shared cache
  - Shared across all fetcher machines on the same host (or cluster)
  - TTL: match the DNS TTL (capped at 300 seconds)
  - Key: "dns:" + hostname
  - Value: serialized IP list + cache timestamp
  - Size: 500,000 active domains x 200 bytes = 100 MB (fits in one Redis)
```

**Why cap at 300 seconds?**

```
DNS TTL is set by the domain owner. Some domains set TTL = 0 (no caching).
Common cases:
  - CDNs (Cloudflare, Akamai): TTL = 60-300 seconds (frequent IP changes)
  - Regular websites: TTL = 3600-86400 seconds (stable IPs)
  - TTL=0 sites: want no caching (usually dynamic DNS, load balancers)

If we honor TTL=0: every fetch to a CDN = full DNS resolution = 50-200ms.
If we cap at 300s: we might use a slightly stale IP, but:
  - CDNs keep old IPs alive for 300+ seconds during transitions
  - The risk of "wrong IP" from 300s-stale cache is extremely low
  - The latency benefit is enormous: 99% DNS cache hit rate

For TTL=0 records specifically:
  - Still cache for 10 seconds (not 0)
  - Reasoning: a crawler fetching 1,000 pages/sec from one CDN domain
    would make 1,000 DNS queries per second without any caching.
    10-second cache reduces this by 10,000x.
  - Risk: 10 seconds of potentially stale IP.
  - Acceptable: CDNs handle graceful IP transitions.
```

---

### 8.3 HTTP Connection Pooling

**Why it matters:**

```
Without connection pooling (new TCP + TLS per request):
  - TCP handshake: 1 round trip = 20-80ms (depending on geographic distance)
  - TLS 1.3 handshake: 1 round trip = 50-200ms
  - Total per-connection setup: 70-280ms
  - For 1,000 pages/sec from 500 domains: lots of new connections

With connection pooling (reuse keep-alive connections):
  - Send next HTTP request on already-open connection: ~0ms setup
  - Savings: 70-280ms per request to the same domain
```

**Per-domain connection pool implementation:**

```
Pool structure (per fetcher process):
  domain_pools: HashMap<hostname, ConnectionPool>

  ConnectionPool for one domain:
  {
    max_connections: 5,       // max 5 concurrent connections per domain
    idle_connections: Deque,  // available connections (LIFO for keep-alive)
    active_count: int,        // how many connections are in use
    last_used: timestamp,     // for pool cleanup
  }

  function get_connection(hostname):
      pool = domain_pools.get_or_create(hostname)
      
      if pool.idle_connections is not empty:
          conn = pool.idle_connections.pop_right()  // LIFO: newest = warmest
          if conn.is_alive():
              pool.active_count += 1
              return conn
          else:
              // Connection died (server closed it). Discard and try again.
              return get_connection(hostname)
      
      if pool.active_count < pool.max_connections:
          conn = open_new_connection(hostname)  // TCP + TLS handshake
          pool.active_count += 1
          return conn
      
      // Pool full: wait for a connection to be returned
      return pool.wait_for_idle_connection(timeout=5s)

  function release_connection(hostname, conn):
      pool = domain_pools[hostname]
      pool.active_count -= 1
      if conn.is_alive() AND conn.keep_alive:
          pool.idle_connections.push_right(conn)
      // If connection is dead, just discard it.

Cleanup (run every 60 seconds):
  for hostname, pool in domain_pools:
      // Close idle connections older than 90 seconds
      // (servers often close keep-alive connections after 60-120s)
      pool.evict_stale_idle_connections(max_idle_age=90s)
      
      // Remove empty pools for domains not seen in 10 minutes
      if pool.is_empty() AND pool.last_used < now() - 10min:
          domain_pools.remove(hostname)

Why max 5 connections per domain?
  - Politeness: too many connections = effectively no rate limit
  - Most servers handle 100+ concurrent connections, but we don't want
    to be the crawler that ties up 50 connections on one domain
  - 5 connections x 1 req/sec each = 5 req/sec max to one domain
    (already more than the default 1 req/sec Crawl-delay)
  - In practice: max_connections is set from Crawl-delay directive:
    if Crawl-delay = 1s, use 1 connection (sequential)
    if no Crawl-delay, use 5 connections (parallel, but still polite)
```

---

### 8.4 Bloom Filter Redis Pipeline

**The problem without pipelining:**

A Bloom filter with k=7 hash functions means checking 7 bits in Redis to
determine if a URL has been seen. Without pipelining:

```
Without pipelining:
  for i in range(7):
      result_i = redis.GETBIT(bloom_key, bit_position_i)
      // Each GETBIT = 1 network round trip = ~0.5ms
  // Total: 7 x 0.5ms = 3.5ms per URL check
  // At 1M URL checks/sec: 3.5 seconds of Redis round trips per second
  // That is clearly impossible on one Redis instance.
```

**With pipelining:**

```
With Redis pipelining:
  pipe = redis.pipeline()
  for i in range(7):
      pipe.GETBIT(bloom_key, bit_position_i)
  results = pipe.execute()
  // All 7 GETBIT commands sent in one network round trip
  // Total: 1 x 0.5ms = 0.5ms per URL check (7x improvement)
  
  url_seen = all(result == 1 for result in results)

For SETBIT (marking URL as seen):
  pipe = redis.pipeline()
  for i in range(7):
      pipe.SETBIT(bloom_key, bit_position_i, 1)
  pipe.execute()
  // All 7 SETBIT commands in one round trip
```

**Pipelining vs. transactions:**

```
Pipeline: send multiple commands, receive all responses at once.
  - NOT atomic: another client can modify bits between your commands.
  - For Bloom filter: that is fine. See Race Condition 1 discussion.
  - Use PIPELINE for best throughput.

Transaction (MULTI/EXEC): all commands execute atomically.
  - Prevents any other client from interleaving.
  - For Bloom filter: adds overhead (MULTI + EXEC = 2 extra round trips).
  - NOT needed here: at-least-once is acceptable.
  - Use PIPELINE, not MULTI/EXEC.
```

---

### 8.5 Content Store Write Batching

**The problem:** Object storage (S3, GCS) PUT calls have high per-call overhead.

```
Without batching:
  - Each page fetch = 1 PUT call to object storage
  - PUT latency: 50-200ms per call
  - At 231 pages/sec per fetcher machine: 231 PUT calls/sec
  - 231 x 100ms = 23.1 seconds of PUT time per second
  - That requires 24 concurrent PUT threads/coroutines just to keep up
  - Object storage bills per API call: 231 x 86400 = 20M calls/day
    At $0.005/1000 PUT calls: $100/day just for API calls on one machine

With batching (buffer 100 pages, write as one multipart upload):
  - Buffer 100 pages in memory (100 x 500KB = 50 MB)
  - Write as one batch to object storage every 10 seconds
    (or when buffer reaches 100 pages, whichever comes first)
  - 100x fewer API calls: 20M/100 = 200K calls/day = $1/day

Implementation pseudocode:
  buffer = []
  last_flush = now()

  async function handle_fetched_page(url, body):
      buffer.append({url, sha256(body), body, now()})
      
      should_flush = (
          len(buffer) >= 100 OR
          now() - last_flush > 10_seconds
      )
      
      if should_flush:
          await flush_buffer()

  async function flush_buffer():
      if buffer is empty:
          return
      
      batch = buffer.copy()
      buffer.clear()
      last_flush = now()
      
      // Write all pages in batch to object storage
      // Use multipart upload or parallel PUTs with a semaphore
      tasks = [object_storage.put(page.sha256, page.body) for page in batch]
      await run_concurrently(tasks, max_concurrency=10)
      
      // Update URL metadata in bulk
      url_db.batch_update([{
          url: page.url,
          sha256: page.sha256,
          fetched_at: page.fetched_at,
          size_bytes: len(page.body)
      } for page in batch])

Tradeoff: batching adds up to 10 seconds of latency before a page is written.
  - For a search index that reindexes every few days, 10s is irrelevant.
  - For a real-time news crawler, reduce batch timeout to 1s.
```

---

## Part 9: Rollout and Operational Safety

Deploying changes to a production crawler is risky. The crawler has stateful
distributed components that must survive a deployment without losing data.

---

### 9.1 What Makes Crawler Deployments Risky

```
Stateful components that must survive deployment:

1. Bloom filter (in Redis)
   - Contains 1B+ URL bits. Takes hours to rebuild.
   - Risk: new code changes how URLs are hashed -> all URLs are "new" again
     -> crawler re-crawls the entire web.
   - Mitigation: never change the Bloom filter hash function without a
     migration plan. New hash = new filter, populated alongside old filter.

2. Kafka consumer offsets
   - Each fetcher machine tracks "which Kafka offset did I last process?"
   - Risk: restart a fetcher without persisting offsets -> replays all
     messages from the beginning -> massive duplicate crawls.
   - Mitigation: always commit offsets before restart. Kafka persists offsets
     durably — restarts are safe if the process commits before stopping.

3. robots.txt cache (in Redis)
   - TTL 24 hours. Contains ~500K domain rules.
   - Risk: new code changes how robots.txt is interpreted -> cached old rules
     are applied with the new code -> inconsistent behavior.
   - Mitigation: after deploying new robots.txt parser, clear the cache
     selectively (or wait 24h for TTL expiry).

4. DNS cache (in Redis)
   - TTL 300s. Lower risk — expires quickly.
   - No special mitigation needed.

5. Connection pools (in-process)
   - Lost on restart. Rebuilt quickly.
   - No special mitigation needed.
```

---

### 9.2 Deployment Stages

```
Stage 1: 1% of fetcher fleet (canary)
  - Deploy new version to 1% of fetcher machines (e.g., 2 out of 200)
  - Monitor for 30 minutes:
    - Error rate: should stay below 0.5% of fetches
    - Kafka consumer lag: should not grow (lag = fetchers not keeping up)
    - robots.txt violations: any 429 responses from external sites?
    - Object storage write failures
  - If any alert fires: immediate rollback (see 9.3)
  - If clean for 30 minutes: promote to Stage 2

Stage 2: 10% of fleet
  - Deploy to 20 out of 200 machines
  - Monitor for 1 hour
  - Same metrics as Stage 1
  - Higher traffic means more edge cases exposed

Stage 3: 50% of fleet
  - Deploy to 100 machines
  - Monitor for 2 hours
  - At this stage, most real-world edge cases will have been hit

Stage 4: 100% of fleet
  - Deploy remaining machines
  - Monitor for 4 hours after full deployment
  - Update runbook if new failure modes were discovered

Total rollout time: ~8 hours (minimum) for a careful deployment.
This seems slow, but a bad crawler deployment can:
  - Get your IPs banned by major websites (hours to resolve)
  - Flood a website's servers (legal and ethical risk)
  - Corrupt the Bloom filter (hours to rebuild)
  - Lose Kafka offsets (trigger full re-crawl)
```

---

### 9.3 Rollback Procedure

**Trigger:** error rate rises above 2% of fetches after deployment.

```
Automatic rollback steps:
1. Traffic cutover (30 seconds)
   - Load balancer routes new Kafka partitions back to old fetcher version
   - New-version fetchers stop consuming (drain in-flight requests first)
   - Old-version fetchers resume consuming

2. Kafka drain (no data loss)
   - Do NOT reset Kafka offsets.
   - Old-version fetchers pick up where new-version left off.
   - Messages in-flight when new-version crashed: Kafka redelivers them
     (at-least-once semantics -- safe due to idempotent writes).
   - Wait for Kafka consumer lag to return to baseline.

3. State cleanup
   - If new code wrote bad data to content store: identify affected SHA256s
     (by timestamp range) and delete them from the URL database.
   - The content objects themselves can remain (they are content-addressed;
     orphaned objects are cleaned up by a weekly garbage collection job).
   - If new code modified robots.txt cache: clear affected keys in Redis.
     TTL expiry will handle the rest.

4. Post-mortem
   - Document: what failed, at what stage, what the blast radius was.
   - Add a new alert or monitoring check to catch this failure mode earlier.
   - Fix the root cause before re-attempting deployment.
```

---

### 9.4 Feature Flags for Safe Rollout

**The pattern:** wrap new behavior in a runtime flag. Deploy the code with the
flag OFF. Turn the flag ON for 1% of traffic. Monitor. Increase gradually.

```
Example: new deduplication algorithm

Old code:
  function is_duplicate(url):
      return bloom_filter.contains(sha256_of_normalized_url)

New code (with feature flag):
  function is_duplicate(url):
      if feature_flag("new_dedup_algo", url) is ON:
          return new_dedup_algorithm(url)
      else:
          return bloom_filter.contains(sha256_of_normalized_url)

Shadow mode (highest safety):
  function is_duplicate(url):
      old_result = bloom_filter.contains(sha256_of_normalized_url)
      new_result = new_dedup_algorithm(url)
      
      if new_result != old_result:
          log_discrepancy(url, old_result, new_result)
      
      return old_result  // Always use old result in shadow mode

Shadow mode benefits:
  - New algorithm runs in production traffic, but its result is ignored.
  - Discrepancies are logged for analysis.
  - Zero risk of new algorithm affecting crawler behavior.
  - After 24 hours of shadow mode with zero unexpected discrepancies:
    flip flag to use new_result instead of old_result.
  - This is the safest possible rollout for a stateful algorithm change.

Feature flag storage:
  - Simple: configuration file on each fetcher machine
  - Better: feature flag service (Redis key with percentage rollout)
    flag_config = {
        "new_dedup_algo": {
            "enabled": True,
            "rollout_percent": 5   // enable for 5% of URLs
        }
    }
  - Rollout function: hash(url) % 100 < rollout_percent
  - Deterministic: same URL always goes to same code path (reproducible)
```

---

## Part 10: Cost and Operational Considerations

A web crawler at Google scale is expensive. Understanding the cost model helps
you make architecture decisions that are cost-efficient, not just technically
correct.

---

### 10.1 Major Cost Drivers

```
Rough cost estimate for 20B pages/month crawler:

1. Egress bandwidth (fetching from external sites)
   - 20B pages x 500KB average = 10 PB/month outbound
   - Wait: we are fetching FROM external sites (inbound to us).
     "Egress" from the perspective of external sites sending to our IPs.
     Our cost: ingress bandwidth (typically free or cheap in cloud pricing).
   - BUT: many cloud providers charge for cross-region data transfer.
   - Fetching 10 PB/month: ~$20,000-50,000/month in data transfer fees
     (varies enormously by cloud provider and region).

2. Object storage (content store)
   - 35 TB/day new data (after dedup, ~70% of the 50TB total is unique)
   - 35 TB x 30 days = 1.05 PB/month stored
   - At $0.023/GB-month (S3 standard): $24,000/month storage
   - PUT API calls: 20B pages/month at $0.005/1000 = $100,000/month
     (without batching -- see why batching is essential!)
   - With batching (100x reduction): $1,000/month for API calls

3. Compute (fetcher fleet)
   - 200 fetcher machines x $0.50/hour (4-core, 16GB machine) 
   - 200 x $0.50 x 24 x 30 = $72,000/month

4. Redis (Bloom filter + DNS + robots cache)
   - Bloom filter: 1.25 GB
   - DNS cache: 100 MB
   - robots.txt cache: 500 MB
   - URL metadata: 100 GB (bloom filter overflow / URL status)
   - Total: ~100 GB Redis
   - At $0.10/GB-month (managed Redis): $10,000/month

5. Kafka (URL frontier)
   - 3 broker cluster, 30-day retention, 10 TB of URL data
   - ~$3,000-5,000/month for managed Kafka

Rough total: ~$130,000-180,000/month
(This is a crude estimate; real numbers depend heavily on cloud provider,
negotiated pricing, and optimization decisions.)
```

---

### 10.2 How to Reduce Costs

**Optimization 1: Conditional GET (If-Modified-Since)**

```
The problem: re-crawling pages that haven't changed wastes:
  - Bandwidth (downloading unchanged content)
  - Compute (parsing, hashing, dedup checking unchanged content)
  - Object storage writes (overwriting with identical content)

The solution: HTTP conditional GET

First fetch:
  GET /page HTTP/1.1
  Host: example.com
  
  Response:
  HTTP/1.1 200 OK
  Last-Modified: Tue, 15 Nov 2024 08:12:31 GMT
  ETag: "abc123def456"
  Content-Length: 45231
  [full page body]

Re-crawl fetch (1 week later):
  GET /page HTTP/1.1
  Host: example.com
  If-Modified-Since: Tue, 15 Nov 2024 08:12:31 GMT
  If-None-Match: "abc123def456"
  
  If page unchanged:
  HTTP/1.1 304 Not Modified
  [NO BODY]
  
  If page changed:
  HTTP/1.1 200 OK
  Last-Modified: Fri, 22 Nov 2024 14:30:00 GMT
  ETag: "xyz789"
  [new page body]

Savings from 304 responses:
  - No body downloaded = saves 500KB per page
  - If 60% of pages return 304 on re-crawl:
    Save 60% of re-crawl bandwidth
    At 20B re-crawls/month: save 6B x 500KB = 3 PB/month of bandwidth
    Significant!

Implementation: store Last-Modified and ETag in URL metadata database.
  Include headers on re-crawl requests.
  If 304: update fetched_at timestamp, skip content store write.
```

**Optimization 2: Prioritize high-value domains**

```
Crawl budget allocation:
  - If you have budget to crawl 20B pages/month, spend it wisely.
  - Top 1M domains by traffic represent ~90% of web value.
  - Bottom 99% of domains represent ~10% of web value.

Prioritized budget:
  - 70% of crawl budget: top 100K domains (crawl frequently, deeply)
  - 20% of crawl budget: top 100K to 1M domains (crawl less frequently)
  - 10% of crawl budget: discovery of new domains from the rest of the web

Cost per unit value:
  - Crawling cnn.com 1,000 times/day: high value per dollar
    (news changes constantly, high traffic, users expect fresh results)
  - Crawling obscure-static-blog.com 1 time/month: also high value per dollar
    (content never changes, low traffic, low priority)
  - Crawling obscure-static-blog.com 100 times/month: wasted dollars
    (no new content, no new value delivered to users)
```

**Optimization 3: Compress content at rest**

```
Raw page bodies: 500KB average
After gzip compression: ~100KB average (5:1 ratio for HTML)

Storage savings:
  - 35 TB/day uncompressed -> 7 TB/day compressed
  - Monthly: 210 TB instead of 1.05 PB
  - Storage cost: $4,800/month instead of $24,000/month

CPU cost of compression: small (gzip is fast)
Network cost to read back: reduced (less data to transfer to downstream
  services like indexers)

Always compress HTML content before writing to object storage.
```

---

### 10.3 On-Call Runbook: Top 5 Alerts

**Alert 1: Fetcher error rate > 2%**

```
What it means: more than 2% of HTTP fetches are returning errors
  (5xx, timeouts, connection refused)

Likely causes:
  A) External site outage (one domain going down causes many errors)
  B) Our fetcher code bug (returns error for valid pages)
  C) Network issue between our fetchers and the internet
  D) We are being rate-limited (receiving 429 Too Many Requests)

Investigation steps:
  1. Break down errors by domain: is one domain causing all errors?
     If yes -> cause A (external outage). Remove that domain from queue
     temporarily using domain blocklist flag.
  2. Break down errors by error type: are they all 429?
     If yes -> cause D (rate limiting). Reduce crawl rate for that domain.
  3. Check if errors started after a recent deployment.
     If yes -> cause B. Rollback the deployment.
  4. Check network: can fetcher machines reach 8.8.8.8?
     If no -> cause C. Escalate to networking team.

Remediation: depends on root cause above.
```

**Alert 2: Kafka consumer lag growing (> 10M messages)**

```
What it means: the URL frontier queue is growing faster than fetchers
  can consume it. Fetchers are falling behind.

Likely causes:
  A) Fetcher throughput dropped (slow pages, external site latency up)
  B) Too many URLs being discovered and enqueued (crawl explosion)
  C) Fetcher machines crashing or restarting
  D) Kafka consumer group rebalancing (temporary, resolves in 30s)

Investigation steps:
  1. Check fetcher CPU and memory: are machines healthy?
  2. Check average fetch latency: has it increased?
     If yes -> external sites are slower. Acceptable. Monitor.
  3. Check enqueue rate: is the link extractor producing URLs faster
     than normal?
     If yes -> possible crawl trap. Check domain URL cap alert.
  4. Check consumer group status: are all fetchers consuming?
     If some are missing -> cause C. Restart stopped fetchers.

Remediation:
  - Short-term: add temporary fetcher capacity (scale out fetcher fleet)
  - Long-term: increase URL cap per domain, or improve link extractor
    crawl trap detection
```

**Alert 3: Redis memory utilization > 80%**

```
What it means: Redis is approaching memory capacity. If it hits 100%,
  it will start evicting data (Bloom filter bits get deleted = false negatives,
  meaning we re-crawl already-seen URLs).

Likely causes:
  A) Bloom filter growing due to new URL discovery spike
  B) DNS cache entries not expiring (TTL misconfiguration)
  C) robots.txt cache growing (too many domains being crawled)

Investigation steps:
  1. redis-cli info memory: check used_memory vs maxmemory
  2. redis-cli --scan --pattern "bloom:*" | wc -l: how many bloom keys?
  3. redis-cli --scan --pattern "dns:*" | wc -l: how many DNS entries?

Remediation:
  - Immediate: increase Redis maxmemory (or add a Redis replica for reads)
  - Short-term: check if Bloom filter needs to be rebuilt
    (high bit density = high false positive rate)
  - Long-term: shard the Bloom filter across multiple Redis instances
    (bloom:shard_0, bloom:shard_1, ... bloom:shard_7)
    Hash URL to shard: shard = hash(url) % 8
```

**Alert 4: Domain rate limit violations (receiving 429 responses)**

```
What it means: we are sending requests to a domain faster than its
  robots.txt Crawl-delay allows. The site is telling us to slow down.

Likely causes:
  A) Crawl-delay in robots.txt was changed (site lowered it, we cached old rules)
  B) Bug in token bucket implementation (bucket rate wrong)
  C) Multiple fetcher machines both crawling the same domain
     (Kafka partitioning failure)

Investigation steps:
  1. Check robots.txt cache for that domain: what Crawl-delay is cached?
     redis-cli get "robots:problematic-domain.com"
  2. Check live robots.txt: curl https://problematic-domain.com/robots.txt
     Compare: did they change the Crawl-delay?
  3. Check Kafka partition assignment: is this domain being consumed by
     more than one fetcher machine?
     kafka-consumer-groups --describe shows which machine owns which partition.

Remediation:
  - Immediate: clear robots.txt cache for that domain
    redis-cli del "robots:problematic-domain.com"
    Fetchers will re-fetch and apply new Crawl-delay.
  - If 429s continue: manually add domain to the "crawl slow" list
    with a 10-second delay until investigation is complete.
  - Long-term: decrease robots.txt cache TTL from 24h to 6h for domains
    that frequently change their Crawl-delay.
```

**Alert 5: Content store write failures > 0.1%**

```
What it means: object storage PUT calls are failing. Pages fetched are not
  being stored. Data loss risk.

Likely causes:
  A) Object storage service outage
  B) Storage bucket full (quota exceeded)
  C) IAM permission issue (credentials expired or revoked)
  D) Network partition between fetchers and storage region

Investigation steps:
  1. Try a manual PUT: aws s3 cp test.txt s3://crawler-content/test.txt
     Can you write at all?
     If no -> causes A, B, C, or D.
  2. Check storage service status page (AWS/GCP/Azure status dashboard).
  3. Check bucket usage: is it near the quota?
  4. Check IAM credentials: when do they expire?
     For long-running services, use instance role credentials (never expire).

Remediation:
  - Immediate: fetcher should buffer failed writes in local memory
    (bounded buffer: max 1GB) and retry with exponential backoff.
    This buys time while the storage issue is resolved.
  - If storage is down > 5 minutes: pause fetchers (stop consuming from Kafka)
    to avoid fetching pages we cannot store.
    Kafka preserves the queue (30-day retention). Resume when storage recovers.
  - Never let fetchers continue fetching without storing -- you waste
    external site bandwidth and lose the data.
```

---

## Interview Q&A -- Most Common Cross-Questions

These are the follow-up questions interviewers ask immediately after your design. Each answer is meant to be said out loud in under 60 seconds.

---

**Q1: What is a URL frontier? Why is it more than just a queue?**

A URL frontier is the data structure that holds all discovered URLs waiting to be crawled. It is more than a plain queue because it must enforce two competing constraints simultaneously: priority ordering (high-authority or stale pages first) and per-domain politeness (never send two requests to the same domain back-to-back without a delay). A flat FIFO queue cannot do both at once. The frontier is typically implemented as two tiers -- a priority tier partitioned into buckets by score, and per-domain FIFO sub-queues within each bucket. Kafka topics partitioned by domain hash give you both properties: Kafka guarantees ordering within a partition (per-domain FIFO), and you drain higher-priority topics first.

---

**Q2: How do you detect duplicate URLs? What data structure do you use and why?**

I use a Bloom filter backed by Redis BITSET. A Bloom filter is a bit array of size m with k hash functions. To insert a URL, set k bit positions derived by hashing the URL. To check if a URL was seen, verify all k bits are set. If any bit is 0, the URL is definitely new. If all k bits are 1, it was probably seen (with a small false positive rate). The reason to prefer this over a hash set is memory: 1 billion URLs fit in 1.25 GB with a Bloom filter, versus roughly 100 GB in a Redis hash set. The trade-off is a ~1% false positive rate, meaning about 10 million URLs per billion get incorrectly skipped and are re-discovered next cycle -- acceptable waste.

---

**Q3: How does a Bloom filter work for URL deduplication? What is its false positive rate and what happens on a false positive?**

A Bloom filter uses k hash functions to map each URL to k bit positions in a large bit array. Insertion sets those k bits to 1; query checks if all k bits are 1. Bits are never reset to 0, which is why false negatives are impossible -- once inserted, a URL's bits stay set. False positives occur when a never-inserted URL's k bit positions happen to all be 1 from other URLs' insertions. For 1 billion URLs, I use m = 9.6 billion bits (1.2 GB) and k = 7 hash functions, giving about 1% false positive rate. On a false positive, the crawler skips a legitimate new URL, treating it as already seen. The cost is that URL is missed this crawl cycle and will be discovered again next cycle when the filter resets. It is wasted opportunity, not a correctness failure.

---

**Q4: What is politeness in a web crawler? How do you implement it?**

Politeness means not hammering any single website with requests faster than it can handle -- a crawler without politeness is functionally a DDoS attack. I implement it with a token bucket rate limiter per domain stored in Redis. The bucket holds up to C tokens and refills at 1 token per second. Each fetch consumes one token; if the bucket is empty, the URL is delayed and the crawler moves to a different domain. I also parse and honor the Crawl-delay directive in robots.txt, which overrides my default rate. Additionally, the URL frontier is partitioned by domain hash in Kafka, so each Kafka partition is one domain's FIFO queue -- the consumer naturally enforces ordering, and the rate limiter gates each dequeue without requiring a separate coordination layer.

---

**Q5: What is robots.txt? Walk through the 6 edge cases.**

robots.txt is a file at the root of every website (example.com/robots.txt) that tells crawlers which paths they may or may not fetch, and at what rate. My crawler fetches it once per domain, caches it for 24 hours, and checks it before every page fetch. The six edge cases: (1) 404 -- file not found means all paths are allowed, per RFC 9309; (2) 5xx server error -- treat as temporarily blocked, retry in 1 hour, do not assume allowed since the server may already be struggling; (3) parse error or malformed content -- be conservative, disallow crawling and log a warning, do not crash; (4) oversized file over 512 KB -- parse only the first 512 KB, ignore the rest; (5) HTTP vs HTTPS mismatch -- robots.txt is scheme-specific, cache them under separate keys so http:// and https:// rules are tracked independently; (6) empty file with 200 status -- empty body means the site explicitly allows everything, which is different from a missing file but has the same result.

---

**Q6: What is the difference between BFS and DFS for crawling? Which do you use and why?**

BFS (Breadth-First Search) processes URLs level by level: all URLs one hop from seeds first, then two hops, and so on. DFS drills deep into one path before backtracking. I use BFS for three reasons. First, breadth: after N fetches with BFS you have touched N different domains, while DFS has explored one domain very deeply -- search engines care about broad coverage. Second, quality: pages one hop from authoritative seeds are likely high-quality; BFS fetches those first. Third, politeness: BFS naturally spreads requests across many domains, while DFS serializes requests to one domain. The only advantage of DFS is memory efficiency (a stack grows as O(depth) vs a BFS queue that grows exponentially), but I solve that by using Kafka as an external disk-backed queue rather than holding the frontier in RAM.

---

**Q7: How do you detect and avoid crawl traps (infinite URL spaces)?**

A crawl trap is a pattern that generates infinite unique-looking URLs for the same content, such as calendar date navigation, randomly generated session IDs in URLs, or adversarial link spam. I use five defenses in combination. First, a depth limit: discard any URL more than 10 hops from a seed. Second, a per-domain URL cap: if a domain contributes more than 100,000 URLs to the frontier, stop accepting new URLs from it and flag it for review. Third, URL normalization: strip session IDs, tracking parameters, and sort query strings, collapsing many trap variants into one canonical URL. Fourth, repeating path segment detection: if a URL path contains the same segment repeated more than three times (like /a/b/c/a/b/c/a/b/c), discard it. Fifth, a URL length limit: discard URLs over 2,048 characters, which are almost always trap-generated.

---

**Q8: How do you handle near-duplicate content detection? What is SimHash?**

URL deduplication is not enough because the same content can appear at different URLs (mirrors, CDNs, URL parameter variants). SimHash detects textual near-duplicates. It works in four steps: tokenize the page into word 3-grams (three consecutive words); hash each 3-gram to a 64-bit number; for each bit position, add +1 if the hash bit is 1 or -1 if it is 0, accumulating weights across all 3-grams; finally, set the SimHash bit to 1 if the weight is positive, 0 if negative. This produces a 64-bit fingerprint. Two pages are near-duplicates if their SimHash fingerprints have a Hamming distance of 3 or less -- meaning at most 3 bit positions differ. SimHash is computed after fetching the page; it runs alongside the SHA256 exact-duplicate check. SHA256 catches identical content; SimHash catches 95%+ similar content.

---

**Q9: How do you handle JavaScript-rendered pages (SPAs)?**

Standard HTML fetching cannot index single-page applications because their content is injected by JavaScript after the initial HTML loads -- a raw HTTP GET returns an empty shell. The full solution is a headless browser fleet: machines running Chromium via Puppeteer or Playwright that load the full page, execute JavaScript, wait for the DOM to stabilize, then extract the rendered HTML. This is expensive: a headless browser consumes 1-4 CPU cores and 512 MB RAM per page, versus 1 CPU millisecond and 1 MB for a raw HTTP fetch. At L5 scope I treat JS-rendered pages as out of scope and note the extension: detect JS-heavy sites by checking for near-empty body with script tags, route those URLs to a separate Puppeteer fleet, and feed the rendered HTML back into the same link extraction and content storage pipeline.

---

**Q10: How do you scale the DNS resolution step -- why is DNS a bottleneck in crawling?**

Each fetcher must resolve the domain name to an IP address before opening a TCP connection. Without caching, a crawler fetching 2,000 pages per second from 2,000 unique domains needs 2,000 DNS queries per second. A public DNS resolver handles 10,000-50,000 queries per second, but each query has a 10-50ms round-trip latency. At 2,000 queries per second each taking 30ms, the fetchers spend more time waiting for DNS than doing anything else and effective throughput collapses. The fix is a two-layer cache: an in-process LRU cache per fetcher machine (10,000 entries, 2 MB) and a shared Redis cache across machines (100 MB for 500,000 active domains). DNS TTLs are capped at 300 seconds regardless of the record's actual TTL. With this setup, over 99% of DNS lookups are cache hits and DNS latency disappears from the critical path.

---

**Q11: What is the difference between a shallow crawl and a deep crawl?**

A shallow crawl fetches only the top-level pages of a website -- typically the home page and pages one or two links deep from the home page. It gives broad coverage across many domains quickly but misses deeper content. A deep crawl follows links recursively to the maximum configured depth, indexing as much of a site as possible including archived content, product detail pages, and paginated lists. Search engines typically use a hybrid: shallow crawl across all known domains to discover new content quickly, and deep crawl for high-authority domains where comprehensive indexing is worth the cost. The depth limit in my design (10 hops from seed) balances these: high-authority sites will naturally have their deeper pages linked from shallower pages and discovered over multiple crawl cycles, while obscure sites are crawled shallowly to stay within budget.

---

**Q12: How do you prioritize which URLs to crawl first?**

Priority is a composite score combining four signals. Domain authority (0 to 1): a pre-computed PageRank-like score for the root domain, updated weekly -- CNN scores near 1.0, a random blog near 0.1. Freshness urgency (0 to 0.5): how long since the page was last crawled -- stale pages get a boost. Link indegree score (0 to 0.3): log10 of the number of inbound links, compressed to prevent very popular pages from dominating. Crawl depth penalty (negative): each hop from a seed URL costs 0.02 priority points, discouraging very deep crawls. URLs with a score above 2.0 go into a Tier 1 Kafka topic; the rest go into Tier 2. Fetchers always drain Tier 1 before touching Tier 2. This ensures breaking news and freshness re-crawls always get bandwidth before background discovery work.

---

**Q13: How do you handle a site that blocks your crawler?**

Sites block crawlers in three ways: rate limiting (429 responses), IP blocking (403 or connection refused), and user-agent blocking (403 specifically for your user-agent). My response to each: for 429 with a Retry-After header, I honor it exactly -- back off for the specified duration, no shorter. For three consecutive 403 responses, I back off 24 hours and alert SRE to investigate whether our rate limiter malfunctioned. For silent blocks (honeypot content or empty responses), I detect them by checking if response bodies are below 500 bytes for pages expected to have content, and flag the domain. The most important rule: I never rotate IPs or spoof user-agents to circumvent blocks. That violates the site's terms of service and potentially computer access laws. The correct response is to back off and respect the site's decision.

---

**Q14: What is link extraction? What challenges arise with relative vs absolute URLs?**

Link extraction is parsing the downloaded HTML to find all outbound hyperlinks -- primarily anchor tags (a href) but also canonical link tags, sitemap references, and redirect headers. The main challenge is that HTML authors write relative URLs like /about or ../images/logo.png, not full absolute URLs. The extractor must resolve these relative paths against the base URL of the page being parsed, which requires tracking the page's own URL and any HTML base tag that overrides it. Additional challenges: filtering out non-HTTP schemes (mailto:, javascript:, tel:, data: URIs must all be discarded), decoding HTML entities in href values, handling malformed URLs that browsers accept through lenient parsing but are technically invalid, and stripping fragment identifiers (#section) since fragments are client-side only and do not represent different server content.

---

**Q15: How do you store crawled pages -- raw HTML, parsed content, or both?**

I store raw compressed HTML in object storage, keyed by SHA256 of the normalized URL plus a timestamp. Raw HTML is the source of truth: downstream consumers (search indexer, PageRank pipeline, spam detector) each extract what they need from it, and storing raw HTML means I never have to re-crawl to get data a new downstream system needs. Storing parsed content would lock in one parsing schema and require re-crawling whenever the schema changes. The content is gzip-compressed before storage, reducing average size from 500 KB to about 100 KB -- a 5x reduction. I also store lightweight metadata separately in a relational database: URL, fetch timestamp, HTTP status code, content hash, redirect chain, and robots.txt ruling. This metadata is cheap to query and serves the scheduler, freshness monitor, and health dashboard without touching the heavy object storage.

---

**Q16: How do you re-crawl pages to keep the index fresh? How do you decide the re-crawl frequency?**

A revisit scheduler tracks each URL's re-crawl interval in a Postgres table indexed by next_crawl_at. The scheduler runs every minute, selects URLs where next_crawl_at is past due, and re-enqueues them to the Kafka frontier. After each re-crawl, I compare the new content hash to the stored hash. If the hash changed, the page is active and I maintain or increase frequency. If it is unchanged for three consecutive visits, I halve the frequency. I use five frequency classes: breaking news at 15 minutes, general news at 1 hour, e-commerce at 1 day, reference content at 7 days, and static documentation at 30 days. There is a per-class minimum (no news page goes below 1 hour) and maximum (no static page gets crawled more than once per day). The goal is to detect changes shortly after they happen without wasting crawl budget on stable content.

---

**Q17: What is the difference between a focused crawler and a general crawler?**

A general crawler like Googlebot tries to index the entire public web, following links across all topics and domains. It uses broad priority signals like domain authority and freshness. A focused crawler targets a specific topic or domain set -- for example a medical research crawler that only follows links related to clinical studies, or a price monitoring crawler that only visits e-commerce product pages. A focused crawler uses a relevance classifier to decide whether a newly discovered URL is worth following: if a page mentions the target topic, follow its links; if not, skip them. This lets a focused crawler achieve much deeper coverage on its topic with the same budget, at the cost of missing off-topic content entirely. Focused crawlers also tend to update more frequently within their domain because their budget is concentrated rather than spread across the entire web.

---

**Q18: How do you handle HTTPS certificate errors during crawling?**

My default behavior matches a browser's strict mode: reject self-signed certificates, expired certificates, and hostname mismatches, log the URL as a TLS error, and do not store any content from that fetch. The reasoning is that a certificate error means we cannot verify we are talking to the genuine server -- the content might be from an attacker's machine. I mark the URL with status tls-error and back off for 24 hours before retrying, in case the certificate is temporarily expired and the site operator will renew it. I do not silently accept invalid certificates, even though many crawlers do, because storing content from an unverified host contaminates the index. If a site operator contacts us saying their certificate is valid but we are still rejecting it, that is a misconfiguration on their end -- we can add them to a manual review queue but will not blanket-disable certificate validation.

---

*Section 5 — L5 / Senior SWE. Very high frequency at Google.*
*~3,500+ lines. Full chapter with algorithm deep dives, race conditions,*
*performance optimization, rollout safety, and operational runbook.*

---

## Interview Simulation — Web Crawler

*45-minute system design interview. Phases follow the Section 2 framework: Requirements → Estimation → API → Data Model → HLD + Deep Dive.*

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a web crawler for a search engine. Where do you start?

**Candidate:** Scale and purpose first. Are we crawling the entire web — billions of pages — or a focused vertical like news sites? What's the target crawl frequency for fresh content: re-crawl popular pages every few hours, or index everything once? Do we need to handle JavaScript-rendered pages (SPAs), or is static HTML sufficient for V1? And what are the output requirements — just raw HTML, or should we extract structured data?

> **Interviewer:** Full web crawl, targeting 5 billion pages. Re-crawl popular pages every 24 hours, long-tail pages every 30 days. JavaScript rendering is out of scope. Output is raw HTML + metadata (URL, crawl timestamp, HTTP headers).

**Candidate:** Good. 5 billion pages is the key constraint that forces a distributed design. One more question: what are the politeness requirements? Do we respect robots.txt strictly, and is there a minimum crawl delay per domain?

> **Interviewer:** Strict robots.txt compliance. Minimum 1 second between requests to the same domain.

**Candidate:** That 1-second per domain minimum is crucial — it means a single crawler can't fetch more than 1 URL/second from any given domain, which shapes the parallelism model. With millions of domains, we need enough workers that each domain's 1-second gap doesn't bottleneck throughput.

*(Cross-question: politeness enforcement)*

> **Interviewer:** You said 1-second minimum between requests to the same domain. How do you enforce this across hundreds of distributed crawler workers without a centralized lock per domain?

**Candidate:** Two-level approach. At the frontier level, URLs are assigned to workers by domain hash — all URLs for `example.com` always go to the same worker shard. This means each shard can enforce politeness locally with a simple in-memory per-domain timestamp map: `last_fetched[domain] = timestamp`, no cross-machine coordination needed. Within a shard, the worker checks `now - last_fetched[domain] >= 1s` before dequeuing a URL for that domain, otherwise it skips to the next domain's URLs. The frontier queue is organized as a per-domain bucket structure so workers can efficiently find a domain that's ready to crawl. This approach scales linearly with the number of shards and eliminates centralized lock contention entirely.

---

### Phase 2: Estimation (8 min)

**Candidate:** Target throughput: 5 billion pages. Popular pages re-crawled every 24 hours, long-tail every 30 days. Let's say 10% of pages are "popular" (500M pages), the rest are long-tail (4.5B). Daily crawl volume: 500M / 1 + 4.5B / 30 = 500M + 150M = ~650M pages/day. That's 650M / 86,400 = ~7,500 pages/second sustained.

Average page size: 200 KB HTML + 50 KB metadata = 250 KB. At 7,500 pages/second: 7,500 × 250 KB = ~1.9 GB/second of raw data to store. Per day: ~160 TB. Over 30 days of retention before archival: ~5 PB. This requires an object store (S3 or GCS) with Hadoop/Spark for downstream processing.

For compute: each crawler worker can fetch roughly 100 pages/second (limited by network I/O, DNS, and connection overhead). To sustain 7,500 pages/second: 75 crawler workers. With politeness constraints and real-world variance, plan for 150-200 workers.

> **Interviewer:** You estimated 200 KB average page size. What if 20% of pages are actually 2 MB due to inline scripts and large DOM trees? How does that affect your design?

**Candidate:** At 20% of 650M pages/day being 2 MB, that's 130M × 2 MB = 260 TB/day from large pages alone, plus 520M × 200 KB = 104 TB from normal pages, totaling ~364 TB/day — more than double my estimate. The storage cost is manageable since object storage is cheap, but the network bandwidth to workers becomes the bottleneck. At 364 TB/day, average bandwidth per worker (150 workers) is ~28 MB/s — achievable on standard 10Gbps NICs. More importantly, I'd add a content size limit: if the Content-Length header or streaming response exceeds 5 MB, abort the fetch and record the URL as "skipped-oversized." Most legitimate web pages are under 2 MB; pages larger than 5 MB are usually binary files or misconfigured servers that aren't useful for search indexing anyway.

---

### Phase 3: API Design (4 min)

**Candidate:** The crawler has two primary APIs — one for URL submission (seeding) and one for crawl status:

```
POST /v1/crawl/seeds
  Body: { urls: ["https://example.com", ...], priority: "high|normal|low" }
  Returns: { job_id, accepted_count, rejected_count }

GET /v1/crawl/status/{url_hash}
  Returns: { url, last_crawled_at, status, next_scheduled_at, http_status }

GET /v1/crawl/domains/{domain}/robots
  Returns: { domain, robots_txt_content, crawl_delay, disallow_paths[], cached_at }

POST /v1/crawl/domains/{domain}/block
  Body: { reason, blocked_by }
  Returns: { domain, blocked_until }
```

Internal components communicate via message queues (Kafka topics for URL frontier, parsed links, crawl results) rather than REST calls.

> **Interviewer:** Why expose a robots.txt cache endpoint as an API rather than just letting workers fetch robots.txt themselves?

**Candidate:** Two reasons. First, politeness: if 150 workers each independently fetch `robots.txt` from `example.com` when they first encounter a URL from that domain, that's 150 requests to the site before we've even fetched a single content page. Centralizing robots.txt fetching means we fetch it once per domain (with a 24-hour TTL), and all workers share the cached result. Second, the parsed robots.txt rules need to be consistently applied — if each worker parses `robots.txt` independently, a parsing edge case could cause different workers to disagree on whether a URL is allowed. Centralized parsing and caching guarantees all workers use the same allow/disallow decision for a given URL.

---

### Phase 4: Data Model (4 min)

**Candidate:** Core tables:

```sql
url_frontier(
  url_hash CHAR(64) PK,         -- SHA-256 of normalized URL
  url TEXT NOT NULL,
  domain TEXT NOT NULL,
  priority FLOAT,               -- higher = crawl sooner
  next_crawl_at TIMESTAMPTZ,
  last_crawled_at TIMESTAMPTZ,
  crawl_interval_hours INTEGER,
  status ENUM('PENDING','IN_FLIGHT','CRAWLED','FAILED','BLOCKED')
)  -- partitioned by next_crawl_at for efficient scheduler queries

crawl_results(
  crawl_id UUID PK,
  url_hash CHAR(64) FK → url_frontier,
  crawled_at TIMESTAMPTZ,
  http_status INTEGER,
  content_type TEXT,
  content_hash CHAR(64),        -- SHA-256 of body (dedup detection)
  s3_path TEXT,                 -- where raw HTML is stored
  links_extracted INTEGER,
  crawl_worker_id TEXT
)

domain_metadata(
  domain TEXT PK,
  robots_txt TEXT,
  robots_cached_at TIMESTAMPTZ,
  crawl_delay_ms INTEGER DEFAULT 1000,
  is_blocked BOOLEAN DEFAULT FALSE
)
```

The URL deduplication for the Bloom filter is handled separately in Redis — the `url_hash` in `url_frontier` is the on-disk authority, while Redis holds a Bloom filter for fast in-memory already-seen checks.

> **Interviewer:** You store `content_hash` in crawl_results. How do you use this to avoid re-indexing pages that haven't changed?

**Candidate:** Before passing a crawled page to the indexer, the crawler computes SHA-256 of the response body and compares it to the `content_hash` from the most recent previous crawl. If they match, the content is unchanged — we update `last_crawled_at` and `next_crawl_at` in `url_frontier` but send a `NO_CHANGE` signal to the indexer instead of the raw HTML. The indexer skips re-parsing and re-indexing, saving significant CPU. This is especially valuable for stable pages that are crawled every 24 hours — many will be unchanged, so content-hash comparison eliminates most indexer work. As a secondary benefit, pages that change content frequently get their `crawl_interval_hours` decremented (more frequent crawls); pages that never change get it incremented (crawl less often). This adaptive crawl frequency saves bandwidth on stable content and keeps fresh content current.

---

### Phase 5: HLD + Deep Dive (20 min)

```
  Seed URLs
      │
┌─────▼────────────┐     ┌──────────────────────────┐
│  URL Frontier    │     │  Bloom Filter (Redis)    │
│  Scheduler       │────▶│  already-seen dedup      │
│  (partitioned by │     └──────────────────────────┘
│   domain hash)   │
└─────┬────────────┘
      │ dequeue ready URLs (domain delay respected)
┌─────▼────────────────────────────────────────────┐
│              Crawler Worker Pool (150+)           │
│  Per worker: fetch → parse → extract links       │
│  DNS cache: 10min TTL per domain                 │
│  Robots.txt: checked before fetch                │
└──┬───────────────┬──────────────────────┬────────┘
   │               │                      │
   ▼               ▼                      ▼
Raw HTML       Extracted links        Crawl metadata
(S3)         (Kafka: new-urls)       (Postgres)
                   │
            ┌──────▼────────┐
            │  Link Processor│
            │  (normalize,  │
            │  dedup, score,│
            │  enqueue)     │
            └───────────────┘
```

*(Cross-question: Bloom filter false positives)*

> **Interviewer:** Your Bloom filter deduplicates already-seen URLs. What's the impact of a false positive — incorrectly marking a new URL as already seen?

**Candidate:** A false positive means we skip crawling a URL we've never actually seen. For a search engine, this means that URL's content doesn't get indexed. The probability is tunable: with a Bloom filter sized at 50 billion bits (~6 GB) for 5 billion URLs, using 7 hash functions, the false positive rate is approximately 1% per URL. That's 1% of new URLs incorrectly skipped — acceptable for a web-scale crawler where completeness is a best-effort goal, not a guarantee. The trade-off against a hash set: a hash set storing 5 billion 64-byte SHA-256 hashes requires 320 GB of memory — prohibitively expensive. The Bloom filter uses 6 GB for a 1% error rate. If we need a lower error rate (0.1%), we size the filter at 100 GB, which is still 3× cheaper than the hash set. For correctness, we back the Bloom filter with the `url_frontier` Postgres table — the Bloom filter is a fast probabilistic pre-filter, and the authoritative dedup is the unique constraint on `url_hash` in Postgres. The Bloom filter prevents most duplicate Postgres lookups; Postgres prevents all actual duplicate crawls.

*(Cross-question: DNS caching)*

> **Interviewer:** You mentioned DNS caching in the workers. What's the failure mode if a domain's IP changes during an active crawl and your cache still has the old IP?

**Candidate:** The crawler sends requests to a stale IP. Three outcomes: (1) the old IP is no longer active — TCP connection refused, the fetch fails with a connection error, and the URL is retried after backoff. The retry will re-resolve DNS if the TTL has expired. (2) The old IP is reassigned to a different server — we might get a 404 or completely unrelated content. Content-hash comparison catches the unrelated content case at the indexer level. (3) The old server is still alive and serving during a blue/green migration — we get valid content from the old deployment, which is usually fine since it's the same content with minor differences. Mitigation: set DNS cache TTL to 10 minutes maximum, and always respect the DNS record's actual TTL if it's shorter. On any TLS certificate hostname mismatch (which would happen if the IP changed to a different domain's server), reject the response and flag for re-resolution. The 10-minute DNS cache is a pragmatic balance between DNS server load reduction and staleness tolerance.

*(Cross-question: distributed coordination)*

> **Interviewer:** With 150 crawler workers all pulling from the URL frontier, how do you prevent two workers from crawling the same URL simultaneously?

**Candidate:** Distributed locking via URL assignment. The frontier scheduler assigns each URL to a specific worker by computing `worker_id = hash(url_hash) % num_workers`. URL-to-worker assignment is deterministic — the same URL always goes to the same worker. When a worker dequeues a URL, it atomically updates `status = IN_FLIGHT` with a `claimed_by` and `claimed_at`. If a worker crashes mid-crawl, a separate watchdog process finds URLs that have been `IN_FLIGHT` for more than 5 minutes (fetch timeout) and resets them to `PENDING` for reassignment. The deterministic hashing prevents two workers from racing to claim the same URL, and the timeout-based recovery handles the worker crash case. An alternative would be using Redis SETNX as a distributed lock per URL, but that adds per-URL Redis writes which is expensive at 7,500 URLs/second.

---

### Common Cross-Questions and Strong Answers

**Q: How does the URL priority queue work, and what signals determine a URL's priority?**

The URL frontier uses a multi-level priority queue. Priority is a float computed from several signals: PageRank estimate of the linking page (URLs linked from high-PageRank pages are more important); freshness decay (URLs not crawled recently get increased priority); domain authority (top-1000 domains by traffic get higher priority); content type signals (sitemaps and RSS feeds get highest priority as they explicitly signal fresh content). Implementation: the frontier is sharded by domain hash across multiple Redis Sorted Sets, where the score is the computed priority. The scheduler pulls URLs by taking the highest-score URL from each domain that has passed its politeness delay. Redis Sorted Sets support O(log N) insert and O(log N) pop-max — efficient for the scheduler's access pattern. For the 5-billion-URL scale, the frontier metadata lives in Postgres (which supports the full history and persistence requirements) while Redis holds only the "ready to crawl" working set — URLs whose `next_crawl_at <= now`, typically a few hundred million at any given time.

**Q: How do you handle crawler traps — pages that generate infinite URLs like `?page=1`, `?page=2`, up to `?page=999999`?**

Three defenses. First, URL normalization: strip or canonicalize common pagination parameters. URLs that differ only in a known pagination parameter (page, offset, p) map to the same canonical URL, and we only crawl the canonical form. Second, per-domain URL count cap: if we've already queued more than 10,000 URLs from a single domain, new URLs from that domain are queued with very low priority and rate-limited to 100 new URLs per day. This prevents a single misbehaving domain from flooding the frontier. Third, path depth limit: URLs with more than 6 path segments (e.g., `/a/b/c/d/e/f/g/page`) are deprioritized heavily, as legitimate content is rarely this deeply nested. These three heuristics catch the vast majority of crawler traps. For adversarial cases (intentionally deceptive URLs with random query parameters), we additionally check if the rendered content hash is similar to already-crawled pages from the same domain using SimHash — pages with >90% SimHash similarity are treated as near-duplicates and skipped.

**Q: What happens when a crawled page returns a 301 redirect? How do you handle redirect chains?**

On a 301 (permanent redirect), the crawler follows the redirect to the destination URL and records a mapping in a `url_redirects` table: `{from_url_hash, to_url_hash, http_status, recorded_at}`. The destination URL is crawled and indexed. The source URL is marked as a redirect in the frontier — future crawls of the source URL skip the fetch and check if the redirect destination still resolves correctly every 7 days. For redirect chains (A → B → C), the crawler follows up to 5 hops before declaring a redirect loop. Each intermediate URL in the chain is recorded. The final destination is the only URL passed to the indexer; intermediate URLs are stored only in the redirect table for link equity calculation. Redirect loops (A → B → A) are detected by tracking the set of URLs visited in the current redirect chain — if we see the same URL twice, we abort with status `redirect-loop` and log all URLs in the cycle. This prevents infinite loops from consuming worker threads.
