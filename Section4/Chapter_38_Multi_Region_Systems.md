# Chapter 36 — Part A: Multi-Region Systems
### Geo-Replication, Latency, and Failure — From Zero to Staff-Level Depth

> "The network is reliable." — First fallacy of distributed computing, L. Peter Deutsch, 1994.
> Multi-region is the discipline of building systems that survive that lie across continents.

---

## Table of Contents

1. What Multi-Region Really Means
2. The Physics of Geography
3. Why Multi-Region Is Hard: The Core Tensions
4. When NOT to Go Multi-Region
5. Understanding "Region" vs "Zone" vs "Edge"
6. Intern to Staff Level Progression on Multi-Region

---

## 1. What Multi-Region Really Means

### The wrong mental model — and why every team starts here

Walk into any engineering planning meeting at a Series B startup, propose going
multi-region, and everyone nods. It sounds mature. It sounds like what Netflix
does. It sounds like the kind of infrastructure that signals "we are serious."

That reaction is the problem.

**Multi-region is not a free upgrade.** Teams hear "deploy to multiple regions"
and picture it like adding more lanes to a highway — same road, just wider, less
congestion. That mental model is wrong in a way that causes real production
disasters.

When you add a second region you are not adding more compute power to the same
system. You are splitting your system into two halves that are physically
separated by thousands of miles and 50-200 milliseconds of network latency. You
are creating two places where your data lives — and those two places will
sometimes disagree about the state of the world. That disagreement is not a bug
to fix. It is the fundamental physics and computer science of running a
distributed system across a planet.

Every region you add is a **consistency decision**. You are now building a
distributed system across data centers separated by oceans.

### The two-restaurant analogy

Imagine you own one restaurant. You have one kitchen, one inventory system, one
refrigerator. When a cook needs to know how many eggs are left, they walk to the
refrigerator and look. The answer is always correct. One source of truth.

Now you open a second restaurant in another city — Paris and New York. You want
both restaurants to share the same menu and the same daily specials. You sync
the inventory list every hour via an automated system.

What happens when a customer in Paris changes their reservation to add three
guests — and the New York reservation system has not yet received that update?
If the New York kitchen tries to seat table 45 based on old data and the Paris
system also seats table 45 at the same time: conflict. Two conflicting versions
of reality about the same customer.

What happens if the internet link between Paris and New York goes down for 20
minutes? Both restaurants keep operating. Both accept new reservations. When the
link comes back, some reservations overlap. Who gets their table?

This is not a hypothetical failure mode. This is what happens in multi-region
systems when you have not designed explicitly for it. The hourly sync is
**database replication**. The 20-minute outage is a **network partition**. The
conflicting reservations are **write conflicts**. Understanding this analogy
deeply — not just nodding at it — is what separates the engineer who copies a
multi-region setup from a blog post and the engineer who designs one correctly.

### The five questions every Staff engineer asks before going multi-region

Before any team goes multi-region, a Staff engineer demands precise answers to
all five of these. Not gestures. Not "we'll figure it out." Answers.

**Question 1: What happens when two regions disagree about the state of the
world?**

During normal operation your regions will almost always agree. But "almost
always" is not "always." Network congestion causes regions to fall behind.
Failover events leave regions completely out of date. You need a concrete answer:
when Region A says the account balance is $200 and Region B says $350, which one
is right? Who wins? What is your conflict resolution strategy? Can you afford to
roll back the losing write? If your answer is "that should not happen," you have
not thought hard enough. It will happen.

**Question 2: What happens during a network partition between regions?**

A **network partition** is when the link between your two regions goes down.
This is not rare. Trans-Atlantic cables get cut by ship anchors. AWS cross-region
links degrade during major events. When the partition happens, each region
continues operating independently. When it heals, you have two diverged histories
to reconcile. What is your plan?

**Question 3: How do you debug a problem that spans three continents?**

A single-region incident is already hard — distributed traces, log correlation,
cascading failures. Now add: the write happened in EU, the read happened in US,
the cache was populated in Singapore, and the user saw stale data in Tokyo. Your
observability stack must handle cross-region trace correlation. Do you have that?

**Question 4: Who is on-call when Tokyo has a problem at 3 AM Pacific?**

Multi-region means multi-timezone on-call. Real multi-region operations require
a follow-the-sun on-call model: teams in each major timezone own their region.
That means hiring, training, and maintaining on-call rotations in multiple
geographic locations. This is a headcount cost that does not show up in an AWS
bill.

**Question 5: Is the 2-3x cost justified by the failure modes you are
preventing?**

Multi-region doubles or triples infrastructure spend. Every compute node, every
database instance, every load balancer, every byte of storage: duplicated per
region. On top of that: cross-region data transfer costs, global load balancer
costs, and increased engineering time on every feature. Run the math.

**If you cannot answer all five questions, you are not ready to go multi-region.**

### The uncomfortable truth about multi-region

Most systems do not need multi-region. This is not a popular statement to make
at a startup, but it is the correct one.

A well-designed single-region system with good disaster recovery is simpler,
cheaper, and often more reliable than a poorly designed multi-region system. The
number of teams that have caused outages by implementing multi-region badly
outnumbers the teams that needed multi-region and did not have it.

Consider the math: if 85% of your users are in the US and EU, two regions in
those areas cover 85% of the latency reduction potential. Adding Tokyo, Sydney,
and Sao Paulo covers the remaining 15% of users — but adds roughly 150%
operational complexity, cost, and risk. The marginal return drops off sharply.

The right question is not "how do we go multi-region?" The right question is:
"Is multi-region the right tool for the problem we actually have?"

### ASCII overview: single-region vs multi-region complexity

```
+---------------------------+     +--------------------------------------------+
|  SINGLE REGION (SIMPLE)   |     |  MULTI-REGION (COMPLEX)                    |
+---------------------------+     +--------------------------------------------+
|                           |     |                                            |
|  [Users globally]         |     |  [EU Users]          [US Users]            |
|         |                 |     |      |                    |                |
|         v                 |     |      v                    v                |
|  [Global Load Balancer]   |     |  [GeoDNS]           [GeoDNS]              |
|         |                 |     |      |                    |                |
|         v                 |     |      v                    v                |
|  [App Servers]            |     |  [EU App Servers]  [US App Servers]        |
|         |                 |     |      |                    |                |
|         v                 |     |      v                    v                |
|  [Single DB Primary]      |     |  [EU DB Primary]   [US DB Primary]        |
|         |                 |     |      |  <-- replication -> |               |
|         v                 |     |      |  (50-200ms lag!)    |               |
|  [DB Replica (AZ-2)]      |     |      v                    v               |
|                           |     |  [EU Replica]      [US Replica]            |
|  Failure modes: clear     |     |                                            |
|  On-call: one timezone    |     |  Failure modes: MANY (split-brain,         |
|  Debugging: one system    |     |  replication lag, partition, conflict)     |
|  Cost: 1x                 |     |  On-call: multiple timezones              |
|                           |     |  Debugging: cross-continent trace         |
|                           |     |  Cost: 2.5-3x                             |
+---------------------------+     +--------------------------------------------+
  ^                                  ^
  Start here. Exhaust this.          Only come here when justified.
```

The arrows between the two database boxes in the multi-region diagram are where
every hard problem lives.

---

## 2. The Physics of Geography

### Why latency has a floor that cannot be optimized away

Every engineer who has ever said "we can optimize our way to lower latency" for
cross-region traffic has run into the same wall: physics.

Light travels through vacuum at 300,000 kilometers per second. In fiber optic
cable, it travels at about two-thirds that speed — roughly **200,000 kilometers
per second** — because glass has a higher refractive index than vacuum and slows
the light down.

Now do the arithmetic:

```
+---------------------------------------------------------------+
|  THE SPEED OF LIGHT PUTS A FLOOR ON CROSS-REGION LATENCY     |
+---------------------------------------------------------------+
|                                                               |
|  Distance: New York to London = ~5,570 km                     |
|  Fiber speed: 200,000 km/sec                                  |
|  One-way minimum: 5,570 / 200,000 = 27.85 ms                 |
|  Round trip minimum: 55.7 ms                                  |
|  Real measured RTT: ~75 ms (cables are not straight)          |
|                                                               |
|  Distance: New York to Tokyo = ~10,800 km                     |
|  One-way minimum: 10,800 / 200,000 = 54 ms                   |
|  Round trip minimum: 108 ms                                   |
|  Real measured RTT: ~150 ms                                   |
|                                                               |
|  Why real > theoretical minimum:                              |
|  - Submarine cables follow ocean floor routes, not            |
|    great-circle paths                                         |
|  - Routing through intermediate network nodes                 |
|  - Queuing delay at routers                                   |
|  - Protocol overhead (TCP, TLS handshake)                     |
|  All of this adds 20-40% on top of the physics minimum.       |
+---------------------------------------------------------------+
```

The implication is direct: if your user is in Tokyo and your server is in New
York, every single request has a 150ms tax. That tax cannot be removed by
writing better code, by buying faster servers, or by optimizing your database
queries. The only way to eliminate it is to move the server (or cache the
response) closer to the user.

This is not an abstract concern. It is the entire reason companies like Netflix,
Cloudflare, and Google run infrastructure on every continent.

### When latency actually hurts your users

Not all latency is equally damaging. Here is the breakdown by operation type:

**API calls**: 150ms is noticeable to users. Google published research showing
that a 100ms increase in search page load time reduced search usage by 0.6%. At
Google's scale that is enormous revenue. For most companies: users notice delays
above 200ms and start complaining at 400ms. A 150ms cross-Atlantic tax puts you
very close to the threshold of user-visible degradation before your application
even runs.

**Web pages with multiple assets**: each asset (image, JavaScript file, CSS
stylesheet) requires a round-trip to fetch. A typical page has 10-30 assets. At
150ms per round-trip, before any render time: 10 assets x 150ms = 1.5 seconds
of pure network overhead. This is why CDNs exist — they eliminate this by
caching assets near the user.

**Database queries with cross-region reads**: this is the killer for poorly
designed multi-region systems. Imagine your database is in US-East and your API
servers are in EU-West. Every database call from your EU API adds one 100ms
round trip. An API endpoint that makes 5 database calls adds 500ms of
cross-region overhead — before any business logic executes, before any data
processing, before your application writes a single byte of response. A
customer-facing product page suddenly takes 600ms longer than it should.

**Read-heavy services**: user profiles, product catalogs, configuration data.
For these, **regional read replicas** dramatically help. EU users read from an
EU replica that was populated by replication from US-East. As long as the data
does not need to be perfectly fresh (product catalog from 30 seconds ago is fine
for browsing), EU users get fast local reads.

**Write-heavy services**: financial transactions, orders, inventory deductions.
Writes still need to go to the authoritative primary. For these, there is no
free lunch — if the primary is in US-East, EU users pay the cross-region latency
on every write. This is why Stripe runs active primaries in multiple regions for
their payment processing, accepting the complexity cost in exchange for low
write latency for EU customers.

### ASCII latency map

```
+-------------------------------------------------------------------+
|         APPROXIMATE ROUND-TRIP LATENCY BETWEEN REGIONS           |
+-------------------------------------------------------------------+
|                                                                   |
|  [us-east-1]  <----  ~75 ms  ---->  [eu-west-1]                  |
|  N. Virginia                         Ireland                      |
|      |                                   |                        |
|      |  <---------- ~200 ms ---------->  |                        |
|      |                              [ap-northeast-1]              |
|      |                               Tokyo                        |
|      |                                   |                        |
|      |  <-------- ~160 ms ---------->    |                        |
|      |                            [ap-southeast-1]                |
|      |                             Singapore                      |
|      |                                                            |
|      |  <------- ~10-15 ms ------>  [us-east-2]                  |
|      |                              Ohio (same continent!)        |
|      |                                                            |
|      |  <------- ~70 ms ------->    [sa-east-1]                  |
|                                     Sao Paulo                     |
+-------------------------------------------------------------------+
|  RTT = round-trip time. One-way is ~half these numbers.           |
|  These are propagation times only. DB query time adds on top.    |
+-------------------------------------------------------------------+
```

Burn this diagram into memory before any system design interview or architecture
review. When someone says "we should add a region in Tokyo," you should
immediately picture that 200ms line to US-East and ask: "Are we planning
synchronous or asynchronous replication? Because synchronous replication means
every write waits 200ms."

### The cross-region database query tax: a worked example

Suppose you are building an e-commerce API at a company like Shopify. Your
database is in us-east-1. You decide to deploy API servers in eu-west-1 to
reduce EU user latency. Your API endpoint for loading a product page makes the
following database calls:

```
1. Fetch product details       (1 DB call)
2. Fetch inventory count       (1 DB call)
3. Fetch pricing rules         (1 DB call)
4. Fetch user's saved address  (1 DB call)
5. Fetch related products      (1 DB call)
                               -----------
Total: 5 database calls
```

In a single-region system (EU API + EU DB): 5 x 2ms = ~10ms of database
network time. Total page load: ~50ms.

In a cross-region setup (EU API + US DB): 5 x 100ms = 500ms of database
network time. Total page load: ~550ms. This is 10x slower purely due to
architecture choices, not code quality.

The fix: add a read replica in EU-West. Product details, pricing rules, and
related products can be read from the EU replica (accepting up to 1-2 seconds of
staleness). Only inventory count (needs to be fresh to avoid oversell) goes to
the US primary. Now: 4 x 2ms (EU replica) + 1 x 100ms (US primary) = 108ms.
Page load: ~158ms. A 3.5x improvement from one architectural change.

This is Staff-level thinking: not "deploy everywhere and hope," but "identify
which queries need freshness and which do not, then minimize the cross-region
hops for the ones that do not."

---

## 3. Why Multi-Region Is Hard: The Core Tensions

### Tension 1: CAP Theorem in the multi-region context

The **CAP theorem** states: a distributed system can guarantee at most two of
these three properties when a network partition occurs — Consistency,
Availability, and Partition Tolerance.

The precise definitions matter:

- **Consistency (C)**: every read returns the most recent write, or an error.
  Not "eventually" — this means right now, the freshest data.
- **Availability (A)**: every request receives a response (not necessarily the
  most recent data). The system always responds.
- **Partition Tolerance (P)**: the system keeps operating even when some nodes
  cannot communicate with each other.

In a single region, network partitions are rare edge cases. You mostly reason
about failure modes of individual machines or availability zones, not of the
entire network fabric going down.

In multi-region, the inter-region network partition is not a rare edge case. It
is a **design scenario you must explicitly plan for**. Submarine fiber cables get
cut by ships and earthquakes. BGP routing failures have caused large-scale
outages. Cloud providers have documented inter-region communication failures.

When the US-East to EU-West link goes down, you have exactly two choices:

**Choice A (Sacrifice Availability)**: stop accepting writes in EU-West until
communication with US-East is restored. EU-West goes read-only. You maintain
consistency — there is only one place writing data — but EU users cannot
complete any write operations (checkout, login, profile update) during the
partition.

**Choice B (Sacrifice Consistency)**: keep accepting writes in EU-West even
though you cannot synchronize with US-East. Both regions diverge. When the link
comes back, you have conflicting writes to reconcile. You maintain availability
— users can always complete operations — but your data is now potentially
inconsistent.

Neither choice is "wrong." It depends entirely on the business. Financial
systems (Stripe, bank transfers, stock trades): sacrifice availability over
consistency. A wrong transaction is catastrophic. Social feeds (Twitter, Reddit,
Instagram): sacrifice consistency over availability. Showing a post from 3
seconds ago instead of 1 second ago is fine. The user can still post and read.

### Tension 2: Strong consistency requires synchronous replication, which adds latency

**Synchronous replication**: the primary region writes the data locally, then
waits for the replica region to confirm it has also written the data, then and
only then responds "success" to the client. Both copies exist before the client
knows the write succeeded.

This is safe. No data loss even if the primary crashes the next millisecond.
Both regions agree on the state of the world at every moment.

The cost: every write waits for a full cross-region round trip. If your primary
is in US-East and your replica is in EU-West (75ms RTT), every write takes an
extra 75ms before the client gets a response. A payment authorization that
normally takes 5ms in a single-region setup now takes 80ms with synchronous
cross-region replication.

At Stripe's scale, they process millions of payment authorizations per day. The
latency cost of synchronous intercontinental replication is why Stripe runs
genuine regional primary nodes — European payments authorize against European
primaries, not against US ones. The synchronous replication is between European
availability zones (0.5ms RTT), not between continents.

When synchronous cross-region replication is worth it: financial data that
cannot be lost or replayed, authentication tokens where a wrong answer enables
account takeover, inventory at hard physical limits (you only have 1 left of
this item, you cannot oversell it).

When it is not worth it: user profile pictures (nobody cares if EU users see a
profile update 2 seconds late), social media like counts (approximate is fine),
view counters and analytics (eventual accuracy is sufficient).

### Tension 3: Asynchronous replication means data can be lost or stale

**Asynchronous replication**: the primary writes locally, immediately responds
"success" to the client, and then sends the write to the replica in the
background. The client does not wait.

This is fast. Users see no additional latency from replication.

The risk: if the primary crashes after acknowledging the write to the client but
before the background replication completes, that write is gone. The replica
never received it. The client thinks the write succeeded. The data is lost.

This is called **replication lag** turning into **data loss**. The window of
risk is the replication lag at the moment of failure. Under normal operation
(50ms replication lag): you could lose at most 50ms of writes. During a 30-
minute network degradation where the replication queue backed up: you could lose
30 minutes of writes.

The staleness problem is separate from data loss. Even without a crash, a user
who just changed their email address in the US region will see their old email
address if their next request is served from the EU replica (which has not yet
received the update). This is called a **stale read**. It is not data loss —
the data will eventually arrive — but it creates confusing user experiences.

| | Synchronous Replication | Asynchronous Replication |
|---|---|---|
| Write latency | Adds 50-200ms (cross-region RTT) | No added latency |
| Data loss on primary failure | Zero (replica already has it) | Up to replication lag window |
| Stale reads possible? | No (both regions always in sync) | Yes (replica may be behind) |
| Best for | Financial data, auth tokens | Catalogs, feeds, preferences |
| Example users | Stripe payments, Google Spanner | Netflix catalog, Twitter feeds |

### Tension 4: The split-brain problem

**Split-brain** is when both regions believe they are the active primary and
both start accepting writes simultaneously.

How it happens: the network link between US-East and EU-West goes down. Each
region can no longer reach the other. Each region's automatic failover system
detects the other region as "unresponsive" and promotes itself to primary. Now
you have two primaries.

User A changes their email address in US-East: `alice@gmail.com`.
User A (on another device) changes their email in EU-West: `alice@yahoo.com`.
Both writes succeed locally. Both users get confirmation.

The network link comes back. Both regions now try to reconcile. They have
conflicting writes for the same record. Which one wins? There is no automatic
answer that is always correct. Last-write-wins by timestamp? Clocks across
regions are not perfectly synchronized — timestamps are unreliable. Application-
defined merge? The application has to define what "merge two email addresses"
means, which is nonsensical.

**This is one of the hardest failure modes in distributed systems.** No generic
automatic resolution is always correct. Every split-brain resolution requires
human judgment or domain-specific rules.

The real incident: GitHub experienced a split-brain incident in 2018 during a
scheduled network maintenance that caused an unexpected 43-second disruption
between their US-East and US-West infrastructure. Their MySQL primary and replica
diverged during that window. The result was over 24 hours of degraded service
while engineers manually reconciled the data and validated consistency. This was
not a poorly designed system — GitHub has extremely competent infrastructure
engineers. Split-brain is simply that hard.

The correct defense against split-brain:

1. **Manual failover only** for consistency-critical systems. Automatic failover
   is convenient but introduces the risk of accidentally promoting a replica when
   the primary is merely slow, not dead. Manual failover adds minutes of delay
   but eliminates split-brain risk.

2. **Fencing and STONITH** (Shoot The Other Node In The Head): before promoting
   a replica to primary, issue a command to guarantee the old primary is shut
   down and cannot accept writes. This requires out-of-band management access
   (IPMI, AWS Systems Manager) to the old primary.

3. **Leader leases**: a leader holds a "lease" (a time-bound exclusive lock from
   a coordination service like ZooKeeper or etcd). If the leader's lease expires
   (because it cannot reach the coordination service), it stops accepting writes
   voluntarily. This prevents two leaders from coexisting because the
   coordination service will only issue one lease at a time.

### Tension 5: Multi-region doubles (or triples) operational complexity

The infrastructure cost is the obvious one — compute, storage, replication
bandwidth — and most teams account for it. The hidden cost is operational
complexity, and teams almost always underestimate it.

**Configuration drift**: a configuration file that is slightly different between
regions (one region uses a 30-second timeout, another uses a 10-second timeout
due to a copy-paste error) causes mysterious per-region behavior differences that
only manifest under specific traffic patterns. These bugs are nearly impossible
to reproduce locally and hard to spot in logs.

**Cross-region debugging**: a bug that only reproduces in the AP region due to
slightly different data patterns or traffic timing. Tracing a request that wrote
in EU and read in US requires distributed trace correlation across two logging
systems, two monitoring systems, two deployment environments.

**Feature development tax**: every feature that touches data must answer the
additional question: "What happens to this feature if the two regions cannot
communicate for 30 seconds? 5 minutes? 2 hours?" This is not a one-time cost.
It is a permanent increase in the mental overhead of every engineer on the team.

**Real cost breakdown** for a team going from 1 region to 3 regions:

```
+--------------------------------------------------+
|  REAL MULTI-REGION COST MULTIPLIER               |
+--------------------------------------------------+
|                                                  |
|  Compute and storage:    2.0x - 3.0x            |
|  Cross-region bandwidth: +$0.02/GB transferred  |
|  (100 GB/day = ~$60/mo, 1 TB/day = ~$600/mo)   |
|  Network infrastructure: +$500-$5,000/month     |
|  Operational tooling:    +15-20% of tooling cost|
|  Engineering overhead:   +15-25% per feature    |
|  On-call staffing:       1-3 additional FTEs    |
|  -----------------------------------------------+
|  ALL-IN MULTIPLIER:      2.5x to 3.0x           |
+--------------------------------------------------+
```

Cloudflare, which genuinely requires multi-region (their product IS the globally
distributed CDN network), employs hundreds of network engineers and SREs
specifically to manage the operational complexity of 200+ points of presence.
The cost is justified because the alternative — not being globally distributed
— would destroy their product entirely. That is the bar for accepting this
complexity.

### ASCII: The five tensions pulling against each other

```
+---------------------------------------------------------------------+
|              THE FIVE MULTI-REGION TENSIONS                         |
+---------------------------------------------------------------------+
|                                                                     |
|          STRONG CONSISTENCY                                         |
|               /\                                                    |
|              /  \                                                   |
|             /    \                                                  |
|            /      \                                                 |
|           /  Hard  \                                                |
|          /  to have \                                               |
|         /   all of  \                                               |
|        / these at   \                                               |
|       /  once        \                                              |
|      /________________\                                             |
|  LOW LATENCY -------- HIGH AVAILABILITY                             |
|      \                /                                             |
|       \              /                                              |
|        \            /                                               |
|    LOW COST      NO SPLIT-BRAIN                                     |
|                                                                     |
|  - Strong Consistency <-> Low Latency: sync replication is slow    |
|  - Low Latency <-> High Availability: fast writes risk data loss   |
|  - High Availability <-> No Split-Brain: active-active risks both  |
|  - No Split-Brain <-> Low Cost: fencing requires extra infra       |
|  - Low Cost <-> Strong Consistency: sync infra is expensive        |
+---------------------------------------------------------------------+
```

Staff-level design does not try to win all five. It explicitly chooses which two
or three tensions to optimize, documents those choices, and builds the system
around the accepted trade-offs.

---

## 4. When NOT to Go Multi-Region

### The right questions to ask first

Before any multi-region proposal, ask these four questions in order. If an
earlier question leads to a simpler solution, stop there.

**Question 1: Where are your users actually located?**

Pull your actual user distribution data from analytics before making any
architectural decision. Do not assume your users are globally distributed. Most
B2B SaaS companies find that 80-90% of their users are in the US and Western
Europe. For those companies, deploying in us-east-1 and eu-west-1 is multi-
region, and it is much simpler than intercontinental distribution.

If 90% of users are in the continental US: deploy in us-east-1 and us-west-2.
Cross-US latency is 60ms, not 200ms. The consistency trade-offs are less severe.
Failover is simpler.

**Question 2: Is your latency problem actually geography, or is it slow code?**

This question sounds insulting but it is important. Before attributing latency
to geography, profile your database queries, check your cache hit rate, review
your serialization overhead, and measure time-to-first-byte versus time-to-load.

A team that moved from a single region in US-East to adding EU-West discovered
their EU latency improved by 40ms. But their real latency problem was unindexed
database queries adding 800ms on average. Geography was 5% of the problem. The
fix was adding database indexes, not adding a region.

**Question 3: Do you need zero-downtime during a regional disaster, or is
15-30 minutes of degradation acceptable?**

This is the question that most honestly separates teams that need multi-region
from teams that just want it. A 30-minute recovery window (RTO of 30 minutes)
is achievable with a well-prepared single-region disaster recovery runbook. You
have a read replica in another region; when the primary region fails, you
promote that replica. Fifteen to thirty minutes of downtime. Most businesses can
survive this without catastrophic revenue impact.

True zero-downtime during a regional failure — where users see no interruption
even as an entire AWS region disappears — requires genuine active-active multi-
region with all the write-conflict complexity that implies.

**Question 4: Do you have the operational maturity for multi-region?**

Small teams (under 20 engineers): almost always no. Not because they lack talent,
but because multi-region doubles the operational surface area and a small team
cannot cover it effectively. The result is a multi-region deployment that is less
well-maintained than a single-region deployment, which means less reliable, not
more.

Netflix has hundreds of infrastructure engineers. Cloudflare has hundreds of
network engineers. Stripe has a dedicated reliability engineering organization.
These companies can afford to do multi-region correctly. A 10-person team
building a SaaS product typically cannot.

### Solutions that are simpler than multi-region

Exhaust these options in order before going full multi-region. Each one
solves a real subset of the multi-region problem at a fraction of the cost.

**CDN (Content Delivery Network)**: Cloudflare, Fastly, and AWS CloudFront
operate 200-300+ edge locations globally. These edge nodes cache static assets
(images, JavaScript, CSS) and serve them from the edge closest to the user.
Setup: a few hours. Cost: very cheap (Cloudflare's free tier covers most small
sites). Benefit: eliminates round-trip latency for static assets, which is the
majority of bytes loaded on most web pages.

For a typical product page that is 60% static assets, a CDN can reduce perceived
page load time by 40-60% for global users — without a single line of application
code changing and without any database complexity. This solves most user
complaints about slow page loads.

**Read replicas in additional regions**: add a database read replica in the
region closest to your users. EU users read from an EU replica. Writes still
go to your US primary. Reads are fast and local. This is dramatically simpler
than full active-active: no write conflict handling, no split-brain risk, no
complex conflict resolution logic. Replication is unidirectional (US primary to
EU replica), so the data flow is simple to reason about.

Amazon RDS supports read replicas in other regions with a few clicks. PostgreSQL
and MySQL both support this natively. The only complexity: application code must
be aware of read vs write endpoints and route accordingly.

**Regional caching (Redis)**: deploy a Redis cluster in each region. Cache hot,
read-frequently data: user profiles, product catalogs, session tokens, pricing
data. EU users read from the EU Redis cluster. Cache misses fetch from the US
primary and populate the EU cache. This reduces cross-region database calls to
cache misses only — typically 5-20% of read traffic for well-cached systems.

This is often the highest-return single improvement for global read latency:
trivial to add, no consistency risk for cached data, enormous latency improvement.

**Single-region disaster recovery with a cross-region DR replica**: this is
the most underused option. Keep your entire production system in one region.
Run it with multi-AZ for local redundancy. Additionally, configure an
asynchronous read replica in a second region. This replica is not serving
production traffic — it is a warm standby for disaster recovery.

If your primary region fails: promote the DR replica to a new primary. This
takes 5-15 minutes with a practiced runbook. Your RPO is the replication lag
at the time of failure — typically 30 seconds to 2 minutes under normal
conditions. Your RTO is 10-20 minutes.

This is the architecture Shopify ran for years. A single authoritative region
with a cross-region DR replica that almost never receives production traffic
but is always warm and ready. Much simpler than active-active. No write
conflicts. No split-brain. Operational complexity close to single-region.

The key operational discipline: practice the failover. Every quarter, run a
full DR drill. Time the failover. Validate data integrity after promotion.
Update the runbook. A DR replica you have never actually promoted is a DR
replica you do not trust. A DR replica you have promoted five times in drills
is one you can promote confidently at 3 AM.

**The decision flow before going full multi-region**:

```
Is the latency problem about static assets?
    YES -> CDN. Done. Do not go further.
    NO  -> Continue.

Is the latency problem about read-heavy database queries?
    YES -> Add regional read replicas + regional caching. Done.
    NO  -> Continue.

Is the availability problem a regional disaster scenario?
    YES, 30 min RTO is fine -> Single-region with cross-region DR replica.
    YES, need <5 min RTO -> Consider multi-region active-passive.
    YES, need zero-downtime -> Multi-region active-active required.

Are you legally required to store data in specific regions?
    YES -> Multi-region required for compliance.
    NO  -> Can you tolerate the operational complexity?
```

### When multi-region IS justified

There are four situations where the cost and complexity are genuinely justified:

**Real-time latency-sensitive global users**: multiplayer games where 200ms
makes the game unplayable, live video platforms, financial trading systems where
millisecond differences matter. Not "nice to have low latency" — "latency above
X ms breaks the core product value."

**Regulatory data residency**: GDPR requires EU user data to stay in EU
infrastructure. CCPA and state-level US data privacy laws add additional
constraints. Banking regulations in various countries require financial data to
stay within their borders. These are legal requirements, not engineering
preferences. You do not have a choice.

**Genuine zero-downtime RTO requirement**: "if our entire primary region goes
dark, we cannot have more than 5 minutes of write downtime." This is a real
requirement for Stripe (cannot stop processing payments for 5 minutes), for
Google (cannot have search go down for 5 minutes), for AWS themselves. The
business case is that the cost of the outage exceeds the cost of multi-region
operations.

**Massive global user base with latency-sensitive writes**: Netflix serves 230+
million subscribers in 190 countries. Even a CDN and regional caching cannot
help with write operations (starting a video, recording your position, updating
your watchlist) that need to go to a database. Netflix's solution: active-active
in multiple regions with eventual consistency for viewing data.

### The wrong reasons to go multi-region — and how to spot them

Even with the right questions, teams rationalize multi-region for wrong reasons.
Recognizing these is a Staff-level skill.

**"We want higher availability."** A well-operated single-region system with
multi-AZ routinely achieves 99.99% availability. Multi-region done poorly
reduces availability. Split-brain incidents and mishandled failovers have taken
down systems that worked perfectly as single-region. Higher availability comes
from better runbooks, better monitoring, and better incident response — not
from more regions.

**"Our competitor is multi-region."** Not a technical reason. Your competitor
may have different requirements, a different user base, or simply ran up a
legacy architecture that grew organically. Copying architecture without copying
context is a good way to inherit complexity without inheriting the need for it.

**"It sounds more scalable."** Multi-region adds geographic distribution, not
horizontal capacity. If you are trying to handle more requests per second, scale
your single-region deployment. Add more API servers. Tune your database. Add
caching. Multi-region does not make your application faster for users who are
already in the same region as your servers — it only helps users in other
geographies.

**"We want to be like Google."** Google runs multi-region because they serve
billions of users globally with billions of dollars in daily revenue. They have
thousands of infrastructure engineers and custom hardware (Google Spanner,
custom network switches, private intercontinental fiber) specifically designed
to make multi-region tractable. When your company reaches equivalent scale, the
comparison becomes relevant. A 15-person engineering team is not at that scale.

The Staff-level test for any multi-region proposal: "Can we quantify the harm
we are preventing and compare it to the cost we are accepting?" If the answer
is "no, it just seems like the right thing to do," it is the wrong thing to do.

### The decision matrix

| User Distribution | Latency Target | Availability Target | Recommended Architecture |
|---|---|---|---|
| 90%+ in one region | < 200ms P99 | 99.9% (8.7 hr/yr ok) | Single region, multi-AZ |
| 70% US, 30% EU | < 100ms P99 | 99.9% | CDN + US primary + EU read replica |
| 50% US, 50% EU | < 100ms P99 | 99.95% (4.4 hr/yr ok) | Active-passive (US primary, EU warm standby) |
| 40% US, 30% EU, 30% APAC | < 100ms P99 | 99.99% (52 min/yr) | Active-passive with 3 regions |
| Truly global | < 50ms P99 | 99.99%+ | Active-active multi-region (full complexity) |
| Regulatory requirement | Any | Any | Multi-region for required geographies |

---

## 5. Understanding "Region" vs "Zone" vs "Edge"

### Availability Zone: the building block

An **Availability Zone (AZ)** is a physically separate data center (or cluster
of very closely co-located buildings) within the same metropolitan area as other
AZs in the same region.

The key properties:
- Independent power feeds, cooling systems, and physical security
- Connected to other AZs in the same region by dedicated, redundant, high-
  bandwidth fiber with latency under 1-2ms
- Close enough geographically that a tornado or earthquake that hits one might
  hit another — they are not disaster-separated, but they are independent from
  a power-grid and equipment-failure perspective

AWS us-east-1 (Northern Virginia) has 6 AZs, labeled us-east-1a through
us-east-1f. Each is a distinct facility in the Northern Virginia area. When AWS
says RDS Multi-AZ keeps a synchronous standby in "another AZ," they mean one
of the other five facilities in Virginia.

Cross-AZ latency: **0.2 to 1 millisecond**. Fast enough to make synchronous
database replication practical. This is why Multi-AZ database deployments can
offer strong consistency at acceptable latency — the replication round trip is
essentially invisible to applications.

AZ failures happen. AWS has had individual AZ failures that affected specific
hardware types, specific services, or networking paths within a single AZ. Multi-
AZ deployment is the baseline requirement for any serious production workload.

### Region: the geographic cluster

A **cloud region** is a geographic cluster of Availability Zones. All AZs in a
region are connected by the cloud provider's private backbone network. They are
in the same country (usually the same metropolitan area) and typically share a
physical presence in a specific city or geographic zone.

Examples:
- **us-east-1**: Northern Virginia — original AWS region, largest in the world
- **eu-west-1**: Dublin, Ireland — primary EU region for AWS
- **ap-northeast-1**: Tokyo, Japan — primary Japan region
- **us-west-2**: Oregon — secondary US region
- **sa-east-1**: Sao Paulo, Brazil — South America

Cross-region latency: **50-200 milliseconds** depending on geography. Cross-
region data transfer: charged separately per GB (approximately $0.02-$0.09/GB
depending on regions). This is why high-volume cross-region replication has a
real dollar cost that shows up in your bill.

AWS has 33 regions globally (as of this writing). GCP has 40+. Azure has 60+.
The number grows every year as each provider expands geographic coverage.

### Edge / Points of Presence (PoP)

**Edge locations** are the infrastructure of content delivery networks (CDNs).
Cloudflare operates 300+ edge locations. AWS CloudFront has 400+. Fastly has
100+. These are not full-scale data centers — they are relatively small, focused
infrastructure nodes designed to cache content and terminate user connections
close to the user.

What edge locations do:
- Cache static assets (images, videos, JavaScript, CSS)
- Terminate TLS so the cryptographic handshake happens close to the user
- Handle HTTP routing and basic request filtering
- Serve cached responses without touching your origin servers at all

What edge locations do not do:
- Run your application business logic
- Store persistent databases
- Handle dynamic, personalized, uncacheable content

The 80/20 insight: for most web applications, 60-80% of traffic is for static
or heavily cacheable content. A CDN edge layer in 300 cities globally handles
that 60-80% with sub-10ms latency worldwide, without any multi-region
complexity. Full multi-region is only needed for the 20-40% of traffic that is
dynamic, personalized, or write-heavy.

### ASCII diagram: Edge, Region, and AZ hierarchy

```
+------------------------------------------------------------------+
|           INFRASTRUCTURE HIERARCHY: EDGE -> REGION -> AZ        |
+------------------------------------------------------------------+
|                                                                  |
|  CLOUDFLARE EDGE POPs          AWS eu-west-1 REGION             |
|  (CDN layer, ~300 globally)    (Full region, Ireland)           |
|  +----------+                  +------------------------------+  |
|  |  London  |                  |  AZ: eu-west-1a              |  |
|  |  PoP     |                  |  [EC2][RDS Primary][Redis]   |  |
|  | (cache,  | ----originreq--> |  +-----------+               |  |
|  |  TLS)   |                  |  eu-west-1b  |               |  |
|  +----------+                  |  [EC2][RDS Standby][Redis]  |  |
|  +----------+                  |  +-----------+               |  |
|  |  Paris   |                  |  eu-west-1c                  |  |
|  |  PoP     | ----originreq--> |  [EC2][Read Replica]        |  |
|  +----------+                  +------------------------------+  |
|  +----------+                                                    |
|  |Frankfurt |  -- cache hit --> user (no origin request!)        |
|  |  PoP     |                                                    |
|  +----------+                                                    |
|                                                                  |
|  The edge layer absorbs most traffic. Only uncacheable requests  |
|  reach the region. AZs inside the region provide redundancy.    |
+------------------------------------------------------------------+
|                                                                  |
|  Key latency numbers:                                            |
|  User in London -> Cloudflare London PoP: ~2 ms                 |
|  Cloudflare London PoP -> AWS eu-west-1 origin: ~10-20 ms       |
|  Total for cached response: ~2 ms  (vs. 75 ms to US-East)      |
|  Total for cache miss (origin fetch): ~15-25 ms                 |
+------------------------------------------------------------------+
```

### The hierarchy as a cost and complexity ladder

Understanding the hierarchy lets you match infrastructure to actual requirement:

| Layer | Solves | Complexity | Cost | Example |
|---|---|---|---|---|
| Single AZ | Single server failure | Low | 1x | Bad idea for production |
| Multi-AZ | Data center failure | Low-Medium | ~1.3x | Baseline for all prod |
| CDN Edge | Static asset latency globally | Very Low | 1.1x | Cloudflare free tier |
| Read Replica (cross-region) | Read latency for global users | Medium | 1.5x | RDS Read Replica in EU |
| Active-Passive (cross-region) | Regional disaster recovery | Medium-High | 2x | DR site, manual failover |
| Active-Active (cross-region) | Zero-downtime + write latency | Very High | 2.5-3x | Netflix, Stripe, Cloudflare |

Each rung up the ladder adds complexity. The Staff-level discipline is staying
on the lowest rung that solves your actual problem.

---

## 6. Intern to Staff Level Progression on Multi-Region

### How the thinking evolves at each level

The clearest signal of engineering level on multi-region questions is not what
you know but how you think. Below is the progression across two common interview
and design questions.

**Question A: "How do we reduce latency for EU users?"**

An **intern** hears this and thinks about the obvious solution: deploy
something in Europe. "Put servers in EU!" This is the right direction but
completely underdeveloped.

A **junior engineer** gets more specific: "Add a load balancer that routes EU
traffic to EU-region servers." They are thinking about routing, which is progress.
But they have not thought about what those EU servers do for data.

A **mid-level engineer** thinks about data separation: "Deploy API servers in
EU-West with read replicas from the US primary. Most reads go to EU, writes go
to US primary." They understand the read/write split and the role of replication.

A **senior engineer** adds measurement and nuance: "Identify read versus write
traffic specifically. Serve reads from EU replicas, writes to US primary. Measure
actual replication lag to understand staleness exposure. Identify which endpoints
are most latency-sensitive so we prioritize the right things." They are thinking
in data and trade-offs, not just architecture diagrams.

A **Staff engineer** reframes the question entirely: "For most EU data — user
profiles, catalog, preferences — CDN handles static and regional caching handles
dynamic reads. Read replicas handle the 15% of reads that cannot be cached. Only
payment authorization and authentication writes need true multi-region primary
placement. Before architecting anything, I want to see per-API-endpoint latency
measurements to confirm which 5% of requests account for 80% of user-visible
latency. We might solve this with caching before we need a second region at all."

**Question B: "How do we handle a regional outage?"**

An **intern**: "Set up automatic failover!" Sounds good. Has not thought about
what automatic failover can go wrong (split-brain).

A **junior engineer**: "Active-passive failover — keep a warm standby, promote
it if the primary goes down." Better. But has not thought about RTO/RPO numbers
or the operational runbook.

A **mid-level engineer**: "Active-passive with 5-minute RTO, 30-second RPO via
async replication. Automated health checks trigger failover." Knows the terms.
Has not thought about whether automatic failover is safe.

A **senior engineer**: "I prefer manual failover with a runbook for consistency-
critical systems. Automatic failover risks split-brain if the primary is
degraded but not dead. For our system, 5 extra minutes of manual confirmation is
worth avoiding split-brain risk. I would automate read traffic failover but
require human approval for write failover."

A **Staff engineer**: "Start with SLOs. Our 99.99% availability SLO means 52
minutes of allowed downtime per year. Active-passive with a 10-minute manual
failover window achieves this if we have fewer than 5 regional failures per year,
which is historically true for AWS. Active-active would allow zero-downtime
failover but introduces split-brain risk for our payment data, which has stronger
correctness requirements than availability requirements. The right answer is
active-passive with automated read failover and manual write failover, plus a
runbook that can be executed in under 10 minutes by any on-call engineer. We
measure RTO on every DR drill quarterly."

### The progression table

| Level | "How do we reduce EU latency?" | "How do we handle regional outage?" |
|---|---|---|
| Intern | "Deploy to EU!" | "Fail over automatically!" |
| Junior | "Add EU load balancer routing EU to EU servers" | "Set up active-passive failover" |
| Mid | "EU API servers + read replicas from US primary" | "Active-passive, 5-min RTO, 30-sec RPO via async replication" |
| Senior | "Identify read vs write; EU replicas for reads, US primary for writes; measure replication lag" | "Manual failover with runbook; automatic failover risks split-brain for write path" |
| Staff | "CDN for static, caching for dynamic reads, replicas for 15% uncached reads; only auth and payments need true multi-region; measure per-endpoint latency first" | "SLO-driven: 99.99% = 52 min/yr; active-passive hits this; active-active adds split-brain risk without proportional benefit for our consistency model; automate reads, manual approval for writes" |

### The meta-skill: reframing scope before designing

The deepest Staff-level signal in a multi-region design conversation is the
willingness to challenge the scope of the problem before proposing a solution.

When an interviewer or stakeholder says "we need to go multi-region," the
instinct at every level below Staff is to accept that framing and start drawing
regions. The Staff instinct is to question it: "Why multi-region specifically?
What user problem are we solving? Have we measured the latency or availability
gap? What is the business cost of the current situation compared to the
operational cost of multi-region?" These questions are not obstruction. They are
the difference between building the right thing and the impressive-sounding thing.

Companies like Basecamp and Notion ran as single-region, multi-AZ deployments
at significant scale because they had the discipline to ask "is multi-region
what we need?" and answer "no" honestly. That discipline is what distinguishes
engineering judgment from engineering theater.

### The three Staff-level instincts

**Instinct 1: Separate data by consistency requirement.** Do not apply one
architecture to the whole system. User profiles are different from payment
balances. Catalog data is different from inventory counts. Design the minimum
viable consistency level for each category independently, then build the
infrastructure that serves each correctly.

**Instinct 2: Measure before you architect.** "Our EU users have high latency"
is not a design input — it is a hypothesis. Measure per-endpoint latency
percentiles (P50, P95, P99). Identify the specific APIs that are slow. Determine
whether the latency is geographic, query-related, or cache-related. Build for
the actual problem, not the assumed one.

**Instinct 3: Operational simplicity is a feature.** The system that is simple
enough for your on-call engineer to understand at 3 AM is more reliable than the
architecturally elegant system that requires 30 minutes of context to debug.
Multi-region adds complexity in every dimension. Every increment of complexity
you can avoid is a reliability improvement. Be deeply skeptical of "we need this
for the edge case" arguments. Edge cases have a way of becoming common cases.

### The staff-level framing for multi-region interviews

When an interviewer asks "design a globally available system," the Staff-level
opener is not to start drawing regions. It is to ask:

1. "What are the availability and latency SLOs? What does 99.9% vs 99.99%
   actually mean for this business?"
2. "Where is the user base actually distributed? Do we have data on this or are
   we estimating?"
3. "What is the tolerance for stale data on reads? Is there any data category
   where inconsistency causes direct business harm?"
4. "What is the RTO/RPO requirement? Is 30-minute manual failover acceptable or
   does the business require zero-downtime regional failure handling?"

These questions reframe the conversation from "how do I add regions" to "what
problem am I actually solving." The answers dictate the architecture. Not the
other way around.

Only after those answers should you draw regions.

---

## Chapter Summary: What You Must Know Cold

Multi-region is a trade-off, not an upgrade. Every concept in this chapter
connects back to that single statement.

**The physics constraint**: 75ms US-East to EU-West, 150ms US-East to Tokyo.
These numbers set the floor for everything. Synchronous replication adds this
latency to every write. Asynchronous replication avoids the latency but accepts
the risk.

**The five tensions**: consistency vs latency, availability vs correctness,
split-brain vs availability, operational simplicity vs redundancy, cost vs
reliability. Staff-level design explicitly chooses which tensions to accept
and documents those choices.

**The simpler alternatives**: CDN handles 60-80% of global latency problems.
Regional read replicas handle most of the rest. Full active-active multi-region
is for the remaining narrow set of requirements.

**CAP in multi-region**: partitions between regions are expected, not edge cases.
CP for financial and correctness-critical data. AP for read traffic and non-
critical writes. Never apply one model to the entire system.

**The hierarchy**: edge PoPs (2ms, cache-only) -> Regions (50-200ms, full
infra) -> AZs (0.5ms, within a region). Each layer solves a different problem.

**Level signals**: interns say "deploy to region." Staff say "measure first,
separate data by consistency requirement, exhaust simpler options, then design
minimum viable multi-region for the specific problem."

**The infrastructure hierarchy for your decision making**: edge PoPs handle
static and cacheable content globally at minimal complexity cost. Cross-region
read replicas handle dynamic read traffic at moderate cost. Active-passive with
a DR replica handles disaster recovery at manageable cost. Active-active handles
true zero-downtime and write latency at the highest cost and complexity. Stay
on the lowest rung that solves the actual, measured problem.

**The terms you must use precisely**: RTO (Recovery Time Objective) is how long
the system can be down during a failure. RPO (Recovery Point Objective) is how
much data can be lost. A 99.99% SLA allows 52 minutes of downtime per year.
Replication lag is how far behind a replica is from the primary, measured in
time. Split-brain is when two nodes both believe they are the primary. These
terms should be in your vocabulary before any architecture conversation.

Part B covers: active-active vs active-passive architectures in depth, DNS-
based routing and GeoDNS mechanics, conflict resolution strategies including
CRDTs and last-write-wins, cross-region failover runbooks, and multi-region
architecture walkthroughs of Netflix, Cloudflare, and Stripe.

---
# Chapter 36: Multi-Region Systems — Part B
## The Three Replication Models and Synchronous vs Asynchronous Replication

---

## Before You Start

Part A of this chapter covered why multi-region exists, what CAP theorem means in practice,
and how to think about latency across oceans. This section covers the engine underneath
every multi-region system: the replication model. Think of Part A as "why you go multi-region"
and this section as "how you actually build it."

At an L6 interview, replication models come up as follow-up depth questions:

- "How does your active-passive setup handle a primary failure?" — You need to know the
  failover sequence in detail, including split-brain prevention and STONITH.
- "You want EU users to get fast writes. Walk me through the trade-offs." — You need
  active-active and exactly what conflict resolution costs.
- "What is your RPO and RTO for this design?" — You need sync vs async replication
  mechanics, not just the vocabulary.
- "When would you NOT use active-active even though it sounds better?" — You need to
  articulate the ops complexity and conflict surface area honestly.

This section builds up each answer from first principles. Read slowly. Every paragraph is
load-bearing for an interview.

---

## 1. The Three Replication Models: Overview

Every multi-region system has to answer one fundamental question before anything else:
**which region or regions are allowed to accept writes?**

There are exactly three answers. Each answer produces a different model with a different
set of trade-offs that flow directly from that single decision.

Think about three bank branches in a national network. Customers deposit and withdraw money.

- **Active-Passive**: Only headquarters can process withdrawals. Branch offices can show
  you your balance (reads), but every actual transaction — every write — goes to HQ. Simple.
  One source of truth. No way for two branches to create conflicting account records.

- **Active-Active**: Any branch can process withdrawals. Your balance is synchronized between
  all branches over the course of the day. Much faster for customers who live near a branch.
  But if you walk into two branches at the exact same time and both try to withdraw your
  entire balance, the system has a conflict on its hands and needs a plan.

- **Read-Local, Write-Central**: Any branch can check your balance and print your statement
  (reads, local, fast). Only HQ can actually change your balance — process a deposit or
  withdrawal. Branch offices always have a slightly delayed copy of HQ's records. For most
  customers who check their balance ten times for every transaction they make, this works
  perfectly.

No model is universally correct. The right one depends on your data's consistency requirements,
how your users are distributed geographically, your team's operational capacity, and whether
your write volume is high enough to make write latency a visible problem.

### Quick Comparison Table

| Property             | Active-Passive          | Active-Active              | Read-Local Write-Central  |
|----------------------|-------------------------|----------------------------|---------------------------|
| Write regions        | 1 (primary only)        | All regions                | 1 (central only)          |
| Read regions         | All (replicas)          | All regions                | All (replicas)            |
| Consistency          | Strong (one writer)     | Eventual (conflicts exist) | Strong (one writer)       |
| Write conflicts      | Impossible              | Possible, must resolve     | Impossible                |
| Failover speed       | 30s - 5 min             | Instant (reroute traffic)  | 30s - 5 min               |
| Write latency        | Low (async to primary)  | Low (write to local region)| High for remote users     |
| Read latency         | Low (local replica)     | Low (local)                | Low (local replica)       |
| Complexity to build  | Medium                  | Very high                  | Low to medium             |
| Complexity to operate| Medium                  | Very high                  | Low to medium             |
| Cost                 | Medium                  | High (all regions full)    | Medium                    |
| Best use case        | OLTP, financial, default| User-sharded, CRDT data    | Read-heavy, CMS, content  |

---

## 2. Model 1: Active-Passive (Primary-Replica)

### The Hospital Analogy

Imagine a hospital network with two buildings. Building A — the primary — has the only
operating room. Building B — the replica — has a fully trained backup surgeon watching
every procedure on a live video feed, ready to step in at any moment.

Patients who need surgery always go to Building A. The backup surgeon in Building B
watches every procedure, stays up to date on every patient's case, and is prepared to
take over immediately. If Building A burns down, the hospital administrator promotes
Building B: patients are redirected, and the backup surgeon becomes the active surgeon.

This is active-passive. One region writes. Others watch, stay in sync, and wait.

### How It Works

The **primary** region accepts all reads and all writes. When a write lands on the primary,
it applies the change to its local database, then sends that change to every **replica**
via a **replication stream**. Replicas apply the same changes in the same order the primary
applied them. Replicas can serve read traffic — they have a full copy of the data, just
potentially slightly behind.

```
                      WRITE TRAFFIC (ALL writes route here)
                                  |
                                  v
                     +------------------------+
  EU user (write) -> |   PRIMARY REGION       | <- US user (write)
                     |   us-east-1            |
                     |   [PostgreSQL primary] |
                     +-----------+------------+
                                 |
              +------------------+------------------+
              |   replication stream (WAL shipping) |
              v                                     v
 +----------------------+            +----------------------+
 |  REPLICA REGION      |            |  REPLICA REGION      |
 |  eu-west-1           |            |  ap-southeast-1      |
 |  [reads only]        |            |  [reads only]        |
 +----------------------+            +----------------------+
         ^                                      ^
         |                                      |
  EU user (read, fast)                 Asia user (read, fast)

 EU user writes:   eu browser -> cross-ocean -> us-east-1 (100-150ms RTT)
 EU user reads:    eu browser -> eu-west-1 replica (15-20ms RTT)
```

### Why This Is the Safe Default

Active-passive has one enormous structural advantage over everything else: **write conflicts
are mathematically impossible**. If exactly one region ever writes, two regions can never
write the same record at the same time. The entire conflict-resolution problem that haunts
active-active systems simply does not exist.

The consistency model is easy to reason about for every engineer on the team:

- Read from the primary: always get the latest data.
- Read from a replica: may get slightly stale data (the replication lag window).
- There is exactly one primary at any given time, so there is never any ambiguity about
  which region has the authoritative value.

Most databases default to this model. **PostgreSQL** streaming replication, **MySQL** replica
sets, **MongoDB** secondaries — all active-passive. Most companies start here. Many stay
here permanently, because operational simplicity is worth a great deal at 3am during an
incident.

### Replication Lag: The Hidden Cost

The most important concept to deeply understand about active-passive is **replication lag**
— the gap between what the primary has written and what replicas have received and applied.

**Asynchronous replication** (the default for most production setups) works like this:

1. Client sends write to primary.
2. Primary applies the write to its local storage.
3. Primary immediately responds to the client: "write successful."
4. In the background, primary ships the write to replicas.
5. Replicas apply the write, typically 10-200ms later under normal conditions.

The client sees a fast, local response. The replica catches up a moment later. Under normal
load this lag is 10-100ms, nearly imperceptible. Under heavy write bursts, it can grow to
seconds. During major incidents (when the primary is under extraordinary stress), replication
lag can reach minutes.

This gap creates a specific failure mode called the **read-after-write consistency problem**:

> User updates their email address on the primary at T=0.
> User's next page load is routed to the nearest replica (eu-west-1).
> eu-west-1's replication lag is currently 300ms.
> eu-west-1 still shows the old email address.
> User sees the old email and concludes the update failed.
> User submits the update again. Now you have a duplicate write.

This is a real user experience problem. The data is not permanently lost — the replica will
catch up — but the user cannot know that.

**Solution: sticky reads after writes.** For a configurable window (typically 1-5 seconds)
after any write, route that user's reads back to the primary. Once the window expires and
the replica is almost certain to have caught up, return to routing reads to the nearest
replica. This is usually implemented as a session-level header or a JWT claim with a
"must-read-from-primary-until" Unix timestamp.

```
  NORMAL READ PATH:
    User request -> load balancer -> nearest replica (20ms)

  READ PATH IN THE WINDOW AFTER A WRITE:
    T = 0: User writes -> primary (confirmed)
    T = 0 to T+5s: User reads -> primary (read-your-own-writes guaranteed)
    T > 5s: User reads -> nearest replica (back to normal fast path)
```

### RPO and RTO for Active-Passive

Two numbers every Staff engineer must know how to calculate precisely and explain clearly.

**RPO (Recovery Point Objective)**: how much data can you afford to lose if the primary
dies right now?

With **asynchronous replication**: RPO equals the replication lag at the exact moment of
failure. If the replica was running 5 seconds behind the primary when the primary crashed,
you lose 5 seconds of writes — those are gone forever. Critically, failures tend to happen
during write-heavy spikes, which is exactly when replication lag is at its worst. Real-world
async RPO in production incidents is frequently 30-120 seconds, not the milliseconds you
see in steady-state monitoring.

With **synchronous replication**: RPO = 0 by design. The primary does not confirm a write
to the client until at least one replica has durably acknowledged it. If the primary crashes
the instant after confirming, the data already exists on the replica. Zero data loss is
mathematically guaranteed, not just statistically likely.

**RTO (Recovery Time Objective)**: how long until the system is accepting writes again
after the primary fails?

| Failover Method    | Typical RTO     | Key Risk                                      |
|--------------------|-----------------|-----------------------------------------------|
| Manual failover    | 15-30 minutes   | Slow but human validates before acting        |
| Automated failover | 30s - 2 minutes | Fast but risk of false-positive split-brain   |

The automation trade-off deserves emphasis at the L6 level: automated failover is faster,
but it can trigger on a network blip when the primary is slow but not actually dead. If
the primary comes back online after the network recovers, you briefly have two nodes that
both believe they are the primary — the classic split-brain scenario. Manual failover is
slower but lets a human verify the situation before promoting a replica. Many mature teams
choose manual failover with a practiced runbook precisely to avoid false-positive split-brain.

### The Failover Process in Detail

Failover is the most operationally dangerous process in an active-passive system. Multiple
major production incidents trace back to failover executed incorrectly or at the wrong time.
Walk through each step carefully when explaining this in an interview.

**Step 1 — Detection**: The primary health check fails. Do not trigger failover on a single
failure. Configure N consecutive failures (typically 3-5) before declaring the primary dead.
This avoids flip-flopping on transient blips. A common configuration: 3 failures at 10-second
intervals means 30 seconds minimum before action is taken.

**Step 2 — Quorum decision**: Before declaring failure, require a quorum — typically 2 of 3
replicas must independently agree that the primary is unreachable. This prevents a single
confused monitoring node from triggering failover during a local network issue.

**Step 3 — Replica selection**: Among all replicas, choose the one with the smallest
replication lag. That replica has the most complete copy of the primary's data. Promoting
the most up-to-date replica minimizes data loss.

**Step 4 — Promotion**: The selected replica stops being read-only and starts accepting
write traffic. Its replication receiver process shuts down. Its write path opens.

**Step 5 — DNS update**: The write endpoint (the DNS name your application sends writes
to) is updated to point to the new primary's IP address. DNS TTL for this record should
be kept short (30-60 seconds). During the TTL window, some clients still have the old
IP cached and will get connection errors.

**Step 6 — STONITH** (critical, non-optional): Before any clients can possibly reach the
old primary if it recovers, send a hard kill command to it. **STONITH — Shoot The Other
Node In The Head** — means physically prevent the old primary from accepting writes.
Implementation options: terminate the cloud instance via API, send a power-off command
via IPMI, push a firewall rule that blocks port 5432/3306. STONITH must be attempted
before the new primary is declared ready. If STONITH fails for any reason, the failover
must be paused until the old primary's status is confirmed.

**Step 7 — Replica reconnection**: Remaining replicas (those not promoted) stop replicating
from the dead old primary and reconnect to the new primary to resume replication.

```
  FAILOVER SEQUENCE DIAGRAM:

  Monitor           eu-west-1 (replica)     us-east-1 (PRIMARY)
      |                    |                        |
      |-- health check --->|                        X  (us-east-1 fails)
      |<-- alive ----------|                        |
      |-- health check --------------------------->   X  (no response #1)
      |-- health check --------------------------->   X  (no response #2)
      |-- health check --------------------------->   X  (no response #3)
      |                    |
      | "3 consecutive failures + quorum agreed: primary is down"
      |                    |
      |-- STONITH -------------------------------->   X  (power off us-east-1)
      |                    |
      |-- PROMOTE -------->|  (eu-west-1 becomes new primary)
      |                    |
      |-- update DNS ----->|  (write endpoint -> eu-west-1 IP)
      |                    |
      |  (TTL expires: 30-60 seconds)
      |                    |
  new writes ------------->|  (eu-west-1 accepting writes)
      |                    |
      |  ap-southeast-1 replica reconnects to eu-west-1
```

### Active-Passive Failure Modes

Beyond normal failover, three specific failure patterns catch teams off guard.

**False failover**: Automated failover triggers because of a network partition between the
monitoring system and the primary — not because the primary has actually failed. The primary
is running fine, just temporarily unreachable from the monitoring perspective. A replica is
promoted. When the network partition heals, the old primary is still running and tries to
accept writes. Now you have two primaries simultaneously: split-brain. STONITH is the only
reliable prevention. If STONITH is not executed before promotion, the false failover creates
a worse situation than the original network blip.

**Failback**: After the incident is resolved and the old primary is repaired, you want to
restore it to its original role. This is not straightforward. The old primary missed all writes
that occurred while it was down. Before it can rejoin the cluster — either as a replica or
to be promoted back to primary — it must fully resync from the current primary. For a large
database (hundreds of gigabytes), this resync can take hours. During that entire window, you
are running on a single primary with zero replicas: the highest-risk configuration possible.
**Prevention**: always keep at least two replicas so that during failback you never drop below
one replica for redundancy.

**Cascade failure**: Primary in us-east-1 fails. eu-west-1 is promoted to primary. eu-west-1
was sized to handle replica read traffic (perhaps 20% of total write capacity). Now it must
absorb 100% of write traffic. eu-west-1 begins to degrade under the load. Your second region
is now also failing. You have turned a single-region incident into a global incident.
**Prevention**: always size replicas to handle 100% of primary write traffic, even if that
means paying for idle capacity during normal operations. Idle capacity during normal times
is insurance that pays out during incidents.

### A Concrete RPO/RTO Scenario to Practice With

Suppose your team operates an e-commerce order service. Primary in us-east-1. Read replica
in eu-west-1. Asynchronous replication. Normal replication lag: 200ms.

At 11:45 PM, there is a write burst: a flash sale drives 10x normal write volume. Replication
lag climbs to 45 seconds as the replica falls behind. At 11:47 PM, us-east-1 crashes
(hardware failure, unrelated to the flash sale).

Replay the numbers:

- **RPO in practice**: 45 seconds of writes are on the primary but not yet on the replica.
  Those orders are lost. Customers received order confirmation emails (the application sent
  those before the write hit the database crash window). Now the database has no record of
  those orders. You need a reconciliation process using the email confirmation as the source
  of truth.
- **RTO**: automated failover detects the failure after 3 x 10s health check intervals =
  30 seconds. Promotion takes 10 seconds. DNS TTL is 60 seconds. Total: roughly 100 seconds
  before writes resume. If the DNS TTL was set to 300 seconds, that is 6 minutes of write
  unavailability.

This scenario illustrates why two things matter in practice that are often overlooked:
1. Keep DNS TTL for your write endpoint low (30-60 seconds), even if it costs slightly
   more DNS queries per second.
2. Monitor replication lag continuously. An alert at "lag > 10 seconds" would have fired
   35 seconds before this crash, giving the on-call engineer time to investigate.

### When to Use Active-Passive

- Strong consistency is required: financial ledgers, inventory counts, user authentication.
- The team is small or new to multi-region (simpler to operate, fewer failure modes to reason
  about, clearer on-call runbooks).
- An RTO of 2-5 minutes is acceptable per your SLA.
- Writes are geographically concentrated: if 80% of your users and writes are in one region,
  active-passive routes that majority traffic with no cross-region penalty.
- You want to start simple and add complexity only when you have measured a concrete need.
  The most common mistake in multi-region design is adding active-active complexity before
  there is evidence that active-passive is actually a bottleneck.

---

## 3. Model 2: Active-Active

### The Google Docs Analogy

You and a colleague are both editing the same Google Doc simultaneously. You are in Tokyo.
They are in London. Both of you type at the same time. Google does not make one of you wait
while the other types. You both see each other's changes in near-real-time. The system
handles concurrent edits without either user losing their work.

That is the aspiration of active-active. Multiple regions ALL accept reads AND writes
simultaneously. Every region is a peer. No designated primary. Changes from each region
replicate asynchronously to all others.

The challenge: when you and your colleague both change the same sentence at the same time,
who wins? Google Docs solves this with operational transforms — a sophisticated algorithm
that took years to get right. Your system needs its own answer to that question, and that
answer must be correct for every data type you expose to concurrent writes.

### How It Works

```
       EU USERS                                    US USERS
           |                                           |
           v                                           v
 +---------------------+                   +---------------------+
 |  REGION eu-west-1   |                   |  REGION us-east-1   |
 |  [reads + writes]   | <-- async repl -> |  [reads + writes]   |
 |  Full data copy     |                   |  Full data copy     |
 +----------+----------+                   +----------+----------+
            |                                         |
            +------------------+----------------------+
                               |
                               v
                    +--------------------+
                    |  REGION            |
                    |  ap-southeast-1    |
                    |  [reads + writes]  |
                    |  Full data copy    |
                    +--------------------+
                               ^
                               |
                          Asia users

  All arrows bidirectional. Every write applied locally, then propagated.
  Conflict detection runs when two regions modified the same record concurrently.
```

### The Fundamental Problem: Write Conflicts

Here is a concrete scenario that illustrates exactly why active-active is harder than it looks.

User Alice has a profile record: `{name: "Alice", email: "alice@old.com"}`.

At 3:00:00.050 PM: Alice logs in from London and updates her email.
EU-West applies: `{name: "Alice", email: "alice@new.com"}`.

At 3:00:00.060 PM: Before EU-West's write has replicated to US-East (replication lag is
roughly 100ms), a background normalization job in US-East updates Alice's name.
US-East applies: `{name: "ALICE", email: "alice@old.com"}`.

Now both writes replicate to both regions. Each region has seen both writes. The conflict:
two different versions of the same record, both written after the last synchronized state,
neither having seen the other.

What should the final state be across all regions?

- **Merge both fields**: `{name: "ALICE", email: "alice@new.com"}` — semantically correct,
  but requires the system to understand field-level merge semantics.
- **EU wins (later wall clock)**: `{name: "Alice", email: "alice@new.com"}` — name
  normalization is silently lost.
- **US wins (faster clock)**: `{name: "ALICE", email: "alice@old.com"}` — Alice's email
  update is silently discarded. She will never know.

There is no single universal answer. The system must have a resolution strategy, and that
strategy must be correct for this specific data type.

### Conflict Resolution Strategies

#### Last Write Wins (LWW)

Every write carries a timestamp. When two conflicting writes meet during replication, the
one with the higher timestamp wins. The other write is silently discarded.

Simple to implement. Built into **Cassandra** by default. Available as an option in
**DynamoDB Global Tables**.

The critical weakness is **clock drift**. Server A's clock runs 3 seconds fast. Every
write from Server A carries a timestamp 3 seconds ahead of Server B's actual wall time.
Server A's writes always win in LWW — not because they happened later in real time, but
because the clock is wrong.

```
  WALL CLOCK LWW SILENT DATA LOSS EXAMPLE:

  Server A clock: 3:00:05 PM (5 seconds fast)
  Server B clock: 3:00:00 PM (correct)

  Real event order:
    Real time 3:00:00 -> User writes email="alice@new.com" on Server B.
                         Write timestamp assigned by Server B: 3:00:00.
    Real time 2:59:58 -> Stale background job writes email="old@domain.com" on Server A.
                         Write timestamp assigned by Server A (fast clock): 3:00:03.

  LWW comparison: Server A timestamp (3:00:03) > Server B timestamp (3:00:00).
  LWW winner: Server A.
  Final value: old@domain.com.

  The logically EARLIER and incorrect write won.
  alice@new.com is gone. No error. No log. Silently overwritten.
```

**Safe for**: immutable append-only event logs (where you never conflict on the same record),
session data where occasional stale values are acceptable.
**Unsafe for**: mutable user records, financial data, anything where a wrong resolution has
a real-world consequence that users or auditors will notice.

#### Vector Clocks

Each write carries a **version vector** — one logical counter per region. The vector records
how many writes from each region this version has incorporated.

Version `{eu: 5, us: 3}` means "this version has incorporated 5 writes from eu-west-1 and
3 writes from us-east-1."

When two writes are compared during replication:
- If vector A dominates vector B (every component of A is greater than or equal to the
  corresponding component of B), A is causally after B. B can safely be discarded.
- If neither dominates (some components of A are higher, some of B are higher), these are
  **genuinely concurrent writes** — no causal ordering exists. This is a real conflict
  that must be surfaced to the application layer.

Used by **Amazon Dynamo** (the original 2007 Dynamo paper), **Riak**. The key advantage
over LWW: vector clocks detect exactly when a conflict exists and pass both versions to
the application, instead of silently picking a winner based on a potentially wrong timestamp.

Cost: more metadata per write, more complexity in the application code that must handle
the "two conflicting versions returned" case.

#### CRDTs (Conflict-free Replicated Data Types)

**CRDTs** are data structures designed mathematically such that any two concurrent updates
from any two regions can always be merged into a single consistent result, regardless of
the order the updates arrive. No coordination required. No conflict detection required. The
merge operation is always well-defined and produces the same result regardless of which order
you apply the two updates.

A **G-Counter** (grow-only counter) is the simplest example. Each region has its own slot
in a vector. Regions only ever increment their own slot — they never modify another region's
slot. The global total is the sum of all slots. Merging two G-Counters is: take the maximum
of each slot.

```
  G-COUNTER EXAMPLE:

  Region eu-west-1:      [eu: 42, us:  0, ap:  0]   total: 42
  Region us-east-1:      [eu:  0, us: 17, ap:  0]   total: 17
  Region ap-southeast-1: [eu:  0, us:  0, ap:  8]   total:  8

  Merge all three (max per slot):
                         [eu: 42, us: 17, ap:  8]   total: 67

  Order of merge does not matter. Result is always 67. No conflict possible.
```

Two regions both incremented their own slots simultaneously during a network partition.
When they reconnect, the merge is deterministic and correct. There is no conflict because
no region ever writes to another region's slot.

Other important CRDTs:
- **G-Set**: grow-only set. Any region can add items. Merge = union of all items.
- **OR-Set**: allows both adds and removes. Concurrent add and remove of the same item:
  add wins. This avoids the "observed-remove" anomaly.
- **PN-Counter**: positive/negative counter, allows both increment and decrement.
  Implemented as two G-Counters: one for increments, one for decrements. Total = P - N.

**Redis** uses CRDTs for cluster-wide counters. **Riak** built its entire data model around
CRDTs. **Google Docs** uses Operational Transforms — a related but distinct formalism —
for character-level concurrent editing.

CRDTs impose constraints: not every data type has a natural CRDT encoding. They work for
counters, sets, and registers. They do NOT work for: decrement-below-zero (you cannot
model "inventory that cannot go negative" as a simple CRDT), general field-level updates
where the semantics of a merge depend on business logic, or data where two concurrent
changes are genuinely in conflict and both cannot be honored.

#### Application-Level Conflict Detection and Resolution

When the data has semantic meaning that the database cannot understand automatically,
you write the merge logic yourself and have the system call it.

**Riak** detects a conflict using vector clocks and returns both conflicting versions to
the application on the next read. The application code inspects both, applies whatever
domain-specific logic is appropriate, and writes back the resolved version.

**Figma** and **Notion** use semantic document merging: they understand the structure of
their data models well enough to merge concurrent field-level changes intelligently.

**Amazon's shopping cart** (as described in the original Dynamo paper) uses application-level
merge: additions and removals are tracked as separate operations (deltas) rather than
full-state replacements. Merging two concurrent cart versions means replaying all add and
remove operations from both versions. The result always reflects both users' intentions.

### The User-Affinity Requirement

Here is the most important practical insight about active-active systems at large companies:
**most real active-active deployments prevent conflicts by routing, not by resolving them.**

The technique is **user-affinity routing**: each user's writes always go to the same region,
determined by their user ID. Implementation: `region = hash(user_id) % num_regions`.

User "alice" (hash = 0) always routes to us-east-1. User "bob" (hash = 1) always routes
to eu-west-1. Alice's writes only ever land in one region. Two regions never write Alice's
record simultaneously — eu-west-1 is never even trying to write her data.

```
  WRITE ROUTING WITH USER AFFINITY:

  alice (hash("alice") % 2 = 0) -> us-east-1 (her home region for writes)
  bob   (hash("bob")   % 2 = 1) -> eu-west-1 (his home region for writes)

  us-east-1: primary writes for alice, replica reads for bob's data
  eu-west-1: primary writes for bob, replica reads for alice's data

  Conflict rate under normal operation: near zero.
  Conflict still possible when:
    - Alice travels and her request routes to eu-west-1.
    - A background job in a non-home region touches Alice's data.
    - Alice has two browser sessions open simultaneously in different regions.
```

This is how **Netflix**, **Facebook**, and most large-scale "active-active" systems
actually work in production. It is more precisely described as multi-primary with geographic
user sharding. All regions accept writes (so the label is correct), but conflicts are rare
because user-level write traffic is not concurrent across regions.

### Active-Active and the Split-Brain During a Partition

Network partition: us-east-1 cannot communicate with eu-west-1. Both continue accepting
writes — that is the whole design goal of active-active. During the partition, their states
diverge. Writes landing in us-east-1 are not seen by eu-west-1, and vice versa.

When the partition heals, both sides must reconcile their diverged states. Every record
modified in both regions during the partition is a potential conflict. With user-affinity
routing, most writes are non-conflicting (Alice's writes were all in us-east-1, Bob's all
in eu-west-1). But background jobs, shared counters, or session data that crossed regions
during the partition are now genuine conflicts.

The two options:

**Option 1: Reject writes during the partition** (pause until regions can communicate).
Safe — no conflicts possible. But this sacrifices availability, which defeats the core
purpose of choosing active-active in the first place.

**Option 2: Accept writes during the partition, resolve conflicts on heal**.
You stay available during the partition, but you take on the obligation of correctly
resolving every conflict type that can arise. For CRDT data types, this is automatic
and correct. For general mutable records, this requires application-level merge logic
that must have been written and tested before the incident.

In practice, mature active-active systems use option 2 for CRDT-compatible data (event
logs, counters, sets) and route globally shared mutable state through a single region
to avoid the problem entirely.

### When Active-Active Is the Right Choice

- Data is CRDT-compatible: counters, event logs, sets, append-only records.
- User data has clear geographic ownership enforced via user-affinity routing.
- Write latency is a hard requirement: users in EU and Asia cannot tolerate 100-150ms
  cross-ocean write latency, and your business has validated this with measurement.
- The team has experience operating distributed systems at this level of complexity,
  including engineers who understand conflict resolution on call.
- Real examples: **Cloudflare Workers KV** (designed for global active-active),
  **DynamoDB Global Tables**, **Cassandra** multi-datacenter setups, **Riak** clusters.

### When Active-Active Is the Wrong Choice

- User data is mutable and a wrong conflict resolution produces an incorrect business
  outcome (financial balances, inventory counts, reservation systems).
- The team has fewer than 50 engineers: the operational cost is high, the on-call burden
  is severe, and the expertise required to debug active-active incidents is specialized.
- Conflict resolution logic has not been fully specified before the system is built. Most
  teams who choose active-active without specifying conflict handling upfront discover they
  have a conflict problem in production, under load, during an incident. That is the worst
  possible time to design a merge algorithm.
- The write latency benefit does not actually exist for your workload because writes are
  infrequent: profile updates, account settings, follows. If 95% of your writes are
  user-setting changes that happen once a day per user, the 100ms cross-region write
  penalty is invisible to users.

---

## 4. Model 3: Read-Local, Write-Central

### The National Library Analogy

A national library system has one headquarters and twenty branch offices. All books are
acquired, catalogued, and stored at headquarters. Branch offices receive copies of the catalog
and can lend out books to local patrons — fast, no waiting, no travel to HQ.

If you want to check out a book: walk into your local branch, done in minutes.
If the library wants to acquire a new book: that request goes to HQ. The branch can submit
the request, but HQ processes it. The patron might wait a few days before the new book
appears at the branch. That is fine because acquisitions are rare compared to checkouts.

This is read-local, write-central. Reads are fast, local, and served from the nearest copy.
Writes always travel to the central authority. The model is efficient because the read:write
ratio in most systems is heavily skewed toward reads.

### How It Works

One **central region** receives all writes. It is the single authoritative source of truth.
Multiple **read regions** hold replicas and serve reads locally. Replication flows outward:
central region to all read regions. No write flows from a read region to another read region.

```
                     ALL WRITES
                          |
                          v
           +------------------------------+
           |   CENTRAL WRITE REGION       |
           |   us-east-1                  |
           |   [authoritative primary DB] |
           +-----------+------------------+
                       |
         +-------------+-------------+
         |   async replication       |
         v                           v
+--------------------+   +---------------------+
|  READ REGION       |   |  READ REGION        |
|  eu-west-1         |   |  ap-southeast-1     |
|  [replica, reads]  |   |  [replica, reads]   |
+--------------------+   +---------------------+
        ^                             ^
        |                             |
  EU reads (20ms)            Asia reads (15ms)

  EU user WRITE path:
    EU browser -> eu-west-1 edge -> [forwarded] -> us-east-1 -> written
    -> async replication -> eu-west-1 updated (~100-150ms later)

  EU user READ path:
    EU browser -> eu-west-1 replica -> response (20ms RTT)
```

### The Write Latency Calculation

For a user in Tokyo, with the write primary in us-east-1:

- One-way latency Tokyo to us-east-1: roughly 120ms.
- Round-trip to complete the write and receive confirmation: 240ms minimum.

Is that acceptable? The answer depends entirely on what the write does and how visible
that latency is to the user.

| Write operation              | 240ms acceptable? | Reasoning                                      |
|------------------------------|-------------------|------------------------------------------------|
| "Like" a post                | Yes               | Tap-and-forget, user does not wait for response|
| Update account settings      | Yes               | Infrequent, user expects a form submission     |
| Post a new article (CMS)     | Yes               | Author flow has natural waiting beats          |
| Submit a chat message        | No                | 240ms is visibly slow in real-time chat        |
| Online multiplayer game move | No                | 240ms latency is unplayable                    |
| E-commerce checkout          | Borderline        | With optimistic UX the latency is hidden       |

**Rule of thumb**: if writes are infrequent (fewer than 5% of total requests) and not in
a real-time interactive context, read-local write-central is the pragmatic correct choice.
The 80-95% of requests that are reads all get fast local service. The small percentage of
writes pay the cross-region tax. The user experience is dominated by read latency, not
write latency.

### Read-After-Write Consistency with Replicas

The same problem exists here as in active-passive: a user writes to the central region,
then immediately reads from a local replica that has not yet received the replication.

User changes their profile picture (write to us-east-1):
- Write confirmed at T=0.
- User's next page load routes to eu-west-1 replica.
- eu-west-1 replication lag: 150ms.
- eu-west-1 still shows the old profile picture.
- User thinks the upload failed. Clicks retry. Duplicate writes.

Same solution as active-passive: for a configurable window after a write (typically 1-5
seconds), route that user's reads to the central region. Once the window expires, resume
routing reads to the nearest replica. Implemented via a session cookie or JWT claim
carrying a "read-from-primary-until" expiry timestamp.

### Where This Model Is Used in Production

**Twitter** (early architecture): tweets written to the US primary. Read from regional
replicas globally. The read:write ratio for Twitter is roughly 100:1 — most users read
far more than they tweet. Read-local write-central was a natural fit.

**LinkedIn**: profile writes go to the US primary. Profile reads are served from regional
replicas globally. LinkedIn's read:write ratio on user profiles is similarly skewed.

**Stack Overflow**: question and answer content served from CDN caches and read replicas.
New answers and edits go to the primary. The read:write ratio is hundreds to one.

**GitHub**: repository browsing, file reads, and web UI all served from regional replicas.
A `git push` goes to the primary. For the typical developer workflow (browse and read
many times, push occasionally), this is the correct trade-off. GitHub also uses synchronous
replication for Git objects specifically, so a confirmed push is guaranteed to survive a
single-region failure even though reads come from replicas.

Most **relational databases deployed multi-region** use this model in practice: primary
in us-east-1, read replicas in eu-west-1 and ap-southeast-1. Amazon RDS makes this
configuration straightforward. RDS promotion — making a read replica into the new primary
after a regional failure — takes 5-7 minutes through the console.

### Strengths and Weaknesses

| Aspect                   | Read-Local Write-Central                           |
|--------------------------|----------------------------------------------------|
| Write latency            | High for users geographically far from central     |
| Read latency             | Low — served from nearest replica                  |
| Write conflicts          | Impossible — exactly one writer                    |
| Conflict handling needed | No                                                 |
| Failover complexity      | Medium — same process as active-passive promotion  |
| Operational complexity   | Low to medium                                      |
| Best for                 | Read-heavy systems, content delivery, global reads |

---

## 5. Synchronous vs Asynchronous Replication Deep Dive

This is the mechanism underneath all three models. The choice between sync and async
replication controls your RPO and your write latency directly. Every multi-region design
must specify which mode is used for which data, and be able to explain the trade-off
quantitatively.

### Synchronous Replication: The Zero-Loss Guarantee

In synchronous replication, the primary does not respond to the client until at least one
replica has confirmed it durably received and applied the write. The client waits for that
cross-region round-trip before seeing a response.

```
  SYNCHRONOUS REPLICATION:

  Client          Primary                   Replica
    |                |                          |
    |--- WRITE ----->|                          |
    |                |--- replicate ----------->|
    |                |                          | (replica writes to disk)
    |                |<-- ACK ------------------|
    |<-- OK (done) --|                          |
    |                |                          |
  Write confirmed ONLY after replica ACK.
  If primary crashes right after sending OK: replica has the data. RPO = 0.
  Cost: write_latency = local_write_time + cross_region_RTT
        Example: 5ms local + 100ms RTT = 105ms per write.
```

**When to use synchronous replication**:

- Financial transactions: charging a credit card, debiting an account. A confirmed charge
  that then gets lost on primary crash is a real-money problem.
- User authentication credentials: losing a new account creation or a password change is
  a security and trust issue.
- Order records: losing a confirmed order is a business-critical data loss.

**Stripe** uses synchronous replication for card authorization writes. The 100ms write
latency overhead is invisible next to the existing bank network round-trip time. The
correctness guarantee justifies the cost.

**GitHub** uses synchronous replication for Git objects. When you run `git push` and
GitHub says "done," that push is guaranteed to survive a single-region failure. Users
accept a slightly longer push time for that guarantee.

### Asynchronous Replication: The Performance Default

In asynchronous replication, the primary responds to the client immediately after applying
the write to its local storage. Replication to replicas happens in the background, after
the client has already received the confirmation.

```
  ASYNCHRONOUS REPLICATION:

  Client          Primary                   Replica
    |                |                          |
    |--- WRITE ----->|                          |
    |<-- OK (done) --|                          |
    |                |--- replicate ----------->|  (background, after ACK to client)
    |                |<-- ACK ------------------|  (client already gone)
    |                |                          |
  Write confirmed immediately after local disk write.
  Replica catches up in the background.
  If primary crashes BETWEEN "OK to client" and "replicate to replica":
    that write is LOST. The client was told it succeeded. It did not survive.
  RPO = replication lag at the moment of crash.
```

**Typical replication lag under normal conditions**: 10-200ms.
**Replication lag under heavy write load**: seconds.
**Replication lag during an incident** (write burst causing the failure): 30-120 seconds.
**Real-world async RPO in production incidents**: frequently measured in minutes, not
milliseconds, even in systems that show 50ms lag in normal monitoring dashboards.

**When to use asynchronous replication**:
- Social content: posts, likes, follows. Losing a few seconds of social activity is survivable.
- Analytics event streams: a small gap in events is tolerable and usually recoverable.
- User preferences and settings: losing a theme change or a notification preference is not
  a business-critical event.
- Search indexes: can be rebuilt from the primary if a replica falls behind catastrophically.

### Semi-Synchronous Replication

**MySQL** supports a middle ground: **semi-synchronous replication**. The primary waits
for acknowledgment from at least 1 replica before confirming to the client. It does NOT
wait for all replicas. If the one replica it is waiting for is slow or goes dark, MySQL
falls back to async mode after a configurable timeout (typically 10 seconds).

This reduces but does not eliminate data loss risk, without paying the full latency penalty
of waiting for every replica to confirm. It is the right choice for user account data,
order records, and similar data where losing a write is a real problem but not catastrophic,
and where your RPO target is "under 1 second" rather than strictly zero.

### Replication Lag Monitoring

Monitoring replication lag is non-negotiable. If you do not know your lag, you do not know
your actual RPO — you only know the theoretical one.

**PostgreSQL**:

```sql
-- Run on the replica:
SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;
-- Returns: 00:00:00.047823 (healthy) or 00:05:13.214 (unhealthy)
```

**MySQL**:

```sql
SHOW SLAVE STATUS\G
-- Key field: Seconds_Behind_Master
-- 0 = caught up. > 10 = investigate. > 60 = alert.
```

**What causes replication lag to grow**:

1. **Write burst on primary**: the replica's apply rate cannot keep up with the primary's
   write rate. The queue of unnapplied changes grows.
2. **Network congestion** between primary and replica: packets are queued, bandwidth is
   saturated, replication stream backs up.
3. **Slow replica I/O**: the replica's disk cannot write changes as fast as the primary is
   producing them. Common in cloud environments during I/O-heavy incidents.
4. **Long-running queries on replica**: a blocking read query on the replica delays the
   replication apply thread. This is the most common cause of sudden lag spikes.

**If lag grows unboundedly**: the replica is permanently falling further behind on every
write burst. Eventually it will be so far behind that it must be rebuilt from a full
snapshot of the primary. A full snapshot copy can take hours for a multi-hundred-gigabyte
database and leaves you without a replica — your highest-risk window — during the entire
rebuild.

**Alert thresholds** (practical starting points, adjust for your SLA):
- User-facing data replicas: alert at replication lag > 1 second.
- Analytics or search replicas: alert at replication lag > 60 seconds.
- Disaster-recovery replicas: alert at replication lag > 5 minutes.

### The Hybrid Approach: Sync for Critical Tables, Async for Everything Else

Most production systems at scale do not make a single replication mode choice for the
entire database. They use a **hybrid model**: synchronous for tables where data loss has
a real consequence, asynchronous for high-volume tables where losing a few seconds is
acceptable.

```
  HYBRID REPLICATION EXAMPLE:

  PRIMARY (us-east-1)
       |
       |-- SYNCHRONOUS ------> REPLICA (eu-west-1):
       |                         tables: users, payments, orders, sessions
       |                         client waits for cross-region ACK (105ms per write)
       |
       +-- ASYNCHRONOUS ------> REPLICA (eu-west-1):
                                 tables: events, activity_logs, search_queue, analytics
                                 client gets OK at local write speed (5ms)
                                 replica catches up in background

  Effect:
    payment write latency:    5ms + 100ms RTT = 105ms  (user accepts this for checkout)
    events write latency:     5ms + 0ms RTT   = 5ms    (fast for high-volume stream)
    RPO for payments:         0 (guaranteed by sync)
    RPO for events:           up to ~60s (acceptable for analytics)
```

PostgreSQL supports per-table replication settings via tablespace configuration. MySQL
supports per-table replication filters, though configuration is more involved.

The hybrid model is the correct default for most production systems: strong guarantees
where they matter, high performance where strong guarantees are not needed.

---

## 6. Putting It Together: The L6 Decision Framework

When a multi-region system design question comes up in an interview, work through these
questions in order before naming a model. The questions are the answer — they show the
interviewer that you understand the trade-offs, not just the terminology.

**Question 1: What is the read:write ratio?**
If reads dominate (above 90% of traffic), read-local write-central is likely sufficient.
You get global read latency without the conflict complexity of active-active. Most content,
CMS, and social feed systems live here.

**Question 2: Are writes user-scoped or globally shared?**
User-scoped writes (each user only writes their own records, never another user's) enable
user-affinity routing, which makes active-active practical. Globally shared writes —
inventory counters, financial balances, reservation pools — mean conflicts are unavoidable
in active-active, and active-passive with a single writer is the safer path.

**Question 3: What is the RPO requirement?**
RPO = 0 requires synchronous replication, which adds cross-region RTT to every write.
RPO = seconds means asynchronous is fine, but understand that your real-world RPO under
incident conditions is often minutes, not seconds.

**Question 4: What is the RTO requirement?**
RTO under 60 seconds requires automated failover with STONITH split-brain prevention.
RTO of 1-5 minutes allows manual failover with a practiced runbook. RTO = 0 (zero downtime
during any regional failure) requires active-active — no failover step is possible in that
time window for active-passive.

**Question 5: What is the team's operational capacity?**
Active-active with conflict resolution is fundamentally more complex to operate than
active-passive. On-call engineers must understand distributed conflict scenarios, merge
algorithms, and partition reconciliation. If the team does not have that depth on call,
active-passive is the safer choice even if it is theoretically lower performance.

```
  DECISION FLOWCHART:

  Start
    |
    v
  reads > 90% of traffic?
    YES -> Read-Local Write-Central
    |      Reads: nearest replica. Writes: central region.
    |      Simple. No conflicts. Done.
    NO
    |
    v
  writes are user-scoped (user only writes their own data)?
    YES -> Active-Active with user-affinity routing.
    |      Use CRDT for edge-case conflicts (roaming users, background jobs).
    |      RTO = 0 (no failover step; just reroute traffic).
    NO
    |
    v
  writes touch shared global state (balances, inventory, reservations)?
    YES -> Active-Passive.
    |      Sync replication for critical tables (RPO = 0).
    |      Async replication for high-volume non-critical tables.
    |      Size replicas to 100% of primary write capacity.
    |
    v
  What is the RTO requirement?
    |
    < 60s  -> Automated failover + STONITH + quorum health checks.
    1-5min -> Manual failover with a documented, practiced runbook.
    > 5min -> Manual failover. Simple and appropriate for this use case.
```

The strongest L6 answer frames the model recommendation in terms of what it costs, not
just what it gives you. A model is not "good" or "bad" — it is a set of trade-offs that
are correct for some problems and wrong for others. Picking the right one requires asking
the right questions first.

### Full Comparison: All Three Models Side by Side

Use this table to quickly locate where a given design factor lands across all three models.
Knowing this cold is essential for interviews where the question shifts mid-discussion.

| Factor                    | Active-Passive              | Active-Active                     | Read-Local Write-Central    |
|---------------------------|-----------------------------|-----------------------------------|-----------------------------|
| Write latency (local)     | Low (async local ack)       | Low (local region)                | Low only for central region |
| Write latency (remote)    | High (cross-region)         | Low (write to nearest)            | High (always cross-region)  |
| Read latency              | Low (nearest replica)       | Low (local region)                | Low (nearest replica)       |
| Consistency guarantee     | Strong (single writer)      | Eventual (configurable per type)  | Strong (single writer)      |
| Write conflicts           | Cannot occur                | Can occur, must be handled        | Cannot occur                |
| Conflict resolution code  | None required               | Required (LWW / CRDT / merge)     | None required               |
| Failover during outage    | 30s-5min (promote + DNS)    | Instant (reroute traffic)         | 30s-5min (promote + DNS)    |
| RPO (async)               | Replication lag at failure  | Near zero (wrote locally)         | Replication lag at failure  |
| RPO (sync)                | Zero                        | Zero per region                   | Zero                        |
| RTO = 0 possible?         | No (failover takes time)    | Yes (no failover step needed)     | No (failover takes time)    |
| Data loss type            | Writes after last sync      | Possible conflict resolution loss | Writes after last sync      |
| Ops complexity            | Medium                      | Very high                         | Low to medium               |
| Team size minimum         | Any                         | 50+ engineers recommended         | Any                         |
| Best real example         | Amazon RDS multi-region     | Netflix, DynamoDB Global Tables   | GitHub, Stack Overflow      |

### The Common Interview Mistake: Defaulting to Active-Active

A very common pattern at L5 level and below: the interviewer says "make this system
globally available with low latency everywhere," and the candidate immediately says
"I will use active-active replication."

Active-active sounds superior because every region handles writes (implying lower write
latency for all users) and there is no single point of failure requiring a failover step.
Both of these are true benefits. But the answer skips the most important question entirely:
**what happens when two regions write the same record at the same time?**

A strong L6 answer sounds like this:

"Active-active is attractive for two reasons: low write latency globally and zero-downtime
regional failover. But it introduces write conflicts, and the right response to a conflict
depends entirely on the data type. Before I commit to active-active, I want to understand
the write patterns. If writes are user-scoped — each user only writes their own data and
never touches another user's records — then user-affinity routing lets me assign each user
a home region. Their writes always land in one place. Conflicts become rare edge cases
rather than the normal operating condition, and I can handle them with LWW or CRDT.

If writes touch globally shared state — inventory levels, financial balances, reservation
pools — then two users in two regions can concurrently attempt conflicting writes on the
same record. There is no routing trick that prevents this. In that case, I would use
active-passive and route all writes to the primary. Users far from the primary pay the
cross-region write latency. That is the price of correctness for this data type."

That answer demonstrates that you understand the trade-off structurally, not just by name.
It also shows the interviewer that you ask questions before committing to a pattern —
which is exactly what a Staff engineer does in a real design review.

### The Real World Is Usually a Hybrid

Almost no production system at a large company uses a single replication model for
every table in every service. What you find in practice:

**Service A (user authentication)**: active-passive with synchronous replication.
RPO = 0 on login credentials and sessions. RTO = 2 minutes via automated failover
with STONITH. Users in EU pay the cross-region write latency on account creation and
password changes. Both are acceptable because those operations are infrequent.

**Service B (activity feed)**: active-active with CRDT counters and append-only event
logs. View counts and like counts are G-Counters. Feed events are append-only with LWW
on the rare conflict. User-affinity routing ensures each user's feed is owned by one
region. RTO = 0 — if us-east-1 goes down, users are rerouted to eu-west-1 immediately.

**Service C (content and articles)**: read-local write-central. Articles are written by
a small number of editors (1% of traffic). Articles are read by millions (99% of traffic).
Content replicates asynchronously to all regions. A newly published article takes up to
5 seconds to appear globally. Readers do not notice a 5-second propagation window.

The model is a tool. Use the right tool for each data type and access pattern in your system.
The interview skill is demonstrating that you can identify which tool is correct for each
part of the problem rather than applying one model uniformly.

---

*Next: Chapter 37 covers global load balancing and DNS-based traffic routing — the
mechanism that actually steers users to the correct region and executes traffic failover
at the network layer when a region goes down.*
# Chapter 36: Multi-Region Systems — Part C
## Global Traffic Routing, Failure Scenarios, and Recovery Patterns

---

## Section 1: How User Traffic Is Routed Globally

### Start With an Analogy: The Post Office Network

Imagine you want to send a letter to a company that has offices in Tokyo, London, and Dallas. The company advertises one single mailing address to the whole world. But behind the scenes, the post office looks at your return address, figures out you are in Tokyo, and delivers your letter to the Tokyo office — not Dallas. You never had to know which office existed. The routing decision happened automatically and invisibly, based purely on where you were mailing from.

That is exactly how global traffic routing works on the internet. When a user in Tokyo opens the Uber app and requests a ride, they do not type "Tokyo's IP address." They just tap "Request." Somewhere between that tap and the server that processes it, a chain of routing decisions quietly executes — and almost always, Tokyo's servers end up handling Tokyo's users, London's servers handle London's users, and so on.

At a Staff-level interview, you need to be able to draw this full routing chain from memory. You need to explain every decision point in the chain, describe what each layer gets wrong, and propose a credible fix for each weakness. Let's build that chain layer by layer, from the user's device all the way to the database that stores their data.

---

### The Routing Chain: Five Layers From Tap to Server

A user's request passes through multiple routing layers before it reaches your service code. Each layer makes an independent routing decision. Together, the five layers determine which physical region, which cluster, and which server instance handles any given request.

```
+--------------------+
|   User's Device    |  (browser, mobile app)
+--------------------+
          |
          |  (1) DNS lookup: "where is api.example.com?"
          v
+--------------------+
|   DNS Resolver     |  (ISP resolver, 8.8.8.8, 1.1.1.1)
+--------------------+
          |
          |  (2) Geo-DNS or Anycast returns a region-specific IP
          v
+--------------------+
|  Global LB / Edge  |  (Cloudflare PoP, AWS CloudFront, Fastly)
+--------------------+
          |
          |  (3) TLS termination, DDoS filtering, request inspection
          v
+--------------------+
|  Regional LB       |  (ALB, NGINX, HAProxy inside the region)
+--------------------+
          |
          |  (4) Routes to a healthy service instance in the region
          v
+--------------------+
|  Service Instance  |  (your API server)
+--------------------+
          |
          |  (5) App-layer routing: "is this user's data here?"
          v
+--------------------+
|  DB / Cache        |  (the correct regional database)
+--------------------+
```

You do not need to own all five layers. Your cloud provider or CDN typically owns layers 2 and 3. Your job as a Staff engineer is to know which layers you are responsible for, which layers your cloud provider owns, where each layer can fail you, and what your fallback is when it does.

---

### Layer 1: Geo-DNS — Routing by Geography at DNS Time

**Geo-DNS** is a technique where the DNS server returns different IP addresses to different users based on their geographic location. It is the most common first-hop routing mechanism for large multi-region services — and the one you will reference most often in system design interviews.

Here is the detailed picture of how it works. When your browser wants to connect to `api.example.com`, it sends a DNS query to a resolver: "What IP address is api.example.com mapped to?" A normal (non-geo) DNS server would always return the same IP regardless of who is asking. A Geo-DNS server inspects the source IP address of the DNS query, checks a database that maps IP ranges to geographic regions, and returns a region-specific IP.

```
User in Tokyo (IP: 203.0.113.10)
          |
          |  DNS query: "api.example.com?"
          v
+-------------------------------------------+
|   Route53 (AWS Geo-DNS)                   |
|                                           |
|  Source IP: 203.0.113.10                  |
|  IP-to-geo DB: 203.x.x.x -> Japan        |
|  Japan routing rule -> Tokyo endpoint     |
|  Returns IP: 100.64.1.1                   |
+-------------------------------------------+
          |
          |  Response: "100.64.1.1"
          v
User's device connects to 100.64.1.1
(Tokyo servers)


User in London (IP: 198.51.100.45)
          |
          |  DNS query: "api.example.com?"
          v
+-------------------------------------------+
|   Route53 (AWS Geo-DNS)                   |
|                                           |
|  Source IP: 198.51.100.45                 |
|  IP-to-geo DB: 198.51.x.x -> UK          |
|  UK routing rule -> EU-West endpoint      |
|  Returns IP: 100.64.2.1                   |
+-------------------------------------------+
          |
          |  Response: "100.64.2.1"
          v
User's device connects to 100.64.2.1
(London / EU-West servers)
```

AWS Route53 calls this "Geolocation routing." Google Cloud DNS and Cloudflare both offer equivalent features. The IP-to-geography database powering this is maintained and updated regularly by the DNS provider.

The practical outcome: Tokyo users hit Tokyo servers, London users hit London servers, almost automatically. Most engineering teams just configure their Route53 records and let Geo-DNS handle the rest.

---

### Geo-DNS: Four Places Where It Silently Fails You

Geo-DNS looks simple but has four specific failure modes that will surprise you in production if you do not understand them in advance.

**Failure Mode 1: DNS TTL and the Stale Cache Window**

DNS responses are cached. When Route53 returns "Tokyo's IP is 100.64.1.1," that answer gets cached by the user's ISP resolver, by their home router, and by their operating system for a duration called the **TTL (Time To Live)**. A typical production TTL is 60 to 300 seconds.

Imagine Tokyo goes down at 2:47 AM. You immediately update your Route53 record to point Tokyo users at Singapore instead. Users whose local DNS cache is still holding the old Tokyo IP will keep hitting Tokyo — a dead region — for up to TTL seconds. At TTL=300 seconds, that is a full five-minute window of user-visible failure that you cannot shorten.

The standard fix: keep your TTL low for geo-routed records. A TTL of 30-60 seconds is a reasonable production setting. The trade-off: more DNS queries per second reach Route53, which is tiny additional cost and load.

**Failure Mode 2: IP Geolocation Is ~95% Accurate, Not 100%**

IP geolocation databases map IP ranges to countries with roughly 95% accuracy at the country level. That 5% error rate comes from three common sources:

- **VPN users:** their device IP is in the Netherlands, but they are physically in Brazil. Route53 sends them to an EU region. They get unnecessary cross-Atlantic latency.
- **Corporate proxy servers:** an entire company's traffic appears to originate from a single proxy IP registered in one city. Every employee worldwide looks like they are in, say, New York, regardless of their physical location.
- **ISPs with centralized DNS resolvers:** some ISPs route all their customers' DNS queries through a centralized resolver server registered in a different region from the customers themselves.

For most use cases, 5% misrouting is an acceptable latency penalty. But you cannot rely on Geo-DNS alone for strict data residency requirements — for example, "EU users' data must never leave the EU" — because 5% of EU users might be routed to non-EU servers.

**Failure Mode 3: Basic Geo-DNS Has No Health Awareness**

Plain Geo-DNS maps geography to IP addresses unconditionally. It does not know if Tokyo is healthy or on fire. If Tokyo is completely down, Geo-DNS still returns "100.64.1.1" to users in Japan. They get connection refused errors.

The fix for this is **Route53 Health Checks with DNS Failover**. You configure Route53 to run health checks against your regional endpoints — for example, an HTTP GET to `https://100.64.1.1/health` every 10-30 seconds. If the health check fails N times in a row (you configure N), Route53 marks that region as unhealthy and stops returning its IP. Instead, Route53 returns the next-closest healthy region's IP.

```
Route53 health check config:
  endpoint: https://100.64.1.1/health
  interval: 30 seconds
  failure threshold: 3 consecutive failures

T=00:00: check passes
T=00:30: check passes
T=01:00: check FAILS  (1 of 3)
T=01:30: check FAILS  (2 of 3)
T=02:00: check FAILS  (3 of 3) -> Route53 marks Tokyo UNHEALTHY
T=02:01: Route53 stops returning 100.64.1.1 for Japan queries
T=02:01: Japan queries now return 100.64.3.1 (Singapore failover)
```

This is Route53's built-in active-passive DNS failover. It works, but it requires 90 seconds (3 x 30-second interval) to trigger. That is the detection latency before DNS failover even begins — and then you still have the TTL cache staleness window on top of that.

**Failure Mode 4: TTL Staleness Applies Even With Health Checks**

Route53 stops returning Tokyo's IP after detecting failure. But users whose DNS cache already holds Tokyo's IP will keep hitting Tokyo for up to TTL seconds after the update. Low TTL (30-60 seconds) is your only mitigation. Some large companies (Google, Cloudflare) run TTLs of 10-30 seconds on their health-checked records. Below ~10 seconds, DNS infrastructure overhead increases noticeably.

**Doing the math on worst-case DNS failover time:**

Understanding the worst-case is important for setting SLO commitments. Here is the complete timeline from failure onset to all users redirected:

```
T=0s:     Tokyo servers fail.

T=0s to T=30s: First health check cycle runs.
              Route53 health check interval: 30 seconds.
              First check after failure: up to 30s away.

T=30s:    Health check #1 fails.
T=60s:    Health check #2 fails.
T=90s:    Health check #3 fails.
          -> Route53 marks Tokyo UNHEALTHY.
          -> Route53 stops returning Tokyo IP for new DNS queries.

T=90s+:   New DNS queries return Singapore IP.
          BUT: users with Tokyo IP cached (TTL=60s) still go to Tokyo.

T=90s to T=150s: Existing DNS caches expire.
                 (worst case: user resolved Tokyo DNS at T=89s,
                  their cache expires at T=89+60=T=149s)

T=150s:   Last cached DNS entries expired.
          All users now resolving to Singapore.

TOTAL WORST-CASE: 150 seconds (~2.5 minutes) from failure
to all users redirected.

With TTL=30s and check interval=10s, failure threshold=3:
  worst case = 30s (detection) + 30s (TTL) = 60 seconds
```

At TTL=60s and check_interval=30s, your SLO for DNS-based failover is "all users redirected within 3 minutes of failure onset." That must be explicitly documented. If your SLO requires RTO under 1 minute, Geo-DNS-based failover alone cannot achieve it — you need additional mechanisms such as Anycast (which has no TTL issue) or pre-established cross-region connection pools at the CDN layer.

---

### Layer 2: Anycast Routing — Network-Level Geographic Routing

**Anycast** is a fundamentally different routing technique that sidesteps the DNS TTL problem entirely by moving the routing decision down from the DNS layer to the network layer.

Here is the intuition. In a normal IP network, each IP address is assigned to exactly one physical location — one server, one data center. Routing a packet to that IP always delivers it to that one place. **Anycast breaks this rule**: the same IP address is simultaneously announced from multiple data centers around the world. Network routing protocols then deliver each packet to the nearest data center announcing that IP, based on actual network topology.

The analogy: ten fire stations in a city all share the same phone number. When you call, the telephone network does not perform a lookup — it physically routes your call to the nearest available station. You call one number, the closest station answers. Same number, different destinations depending on where you are calling from.

In Anycast, **BGP (Border Gateway Protocol)** — the routing protocol used by internet backbone routers — is the mechanism. Each participating data center announces "I can route traffic destined for IP 1.2.3.4" via BGP. Every router on the internet learns the shortest path to 1.2.3.4 from its current position. A router in Tokyo learns the shortest path goes through the Tokyo PoP. A router in London learns it goes through the London PoP.

```
Anycast IP: 104.20.1.1 (announced from all Cloudflare PoPs)

Packet from Tokyo user -> destination 104.20.1.1
    |
    v
Tokyo backbone router
    |
    | BGP route table: shortest path to 104.20.1.1 = Tokyo PoP
    v
Cloudflare Tokyo PoP handles request


Packet from Frankfurt user -> destination 104.20.1.1
    |
    v
Frankfurt backbone router
    |
    | BGP route table: shortest path to 104.20.1.1 = Frankfurt PoP
    v
Cloudflare Frankfurt PoP handles request


Packet from Sao Paulo user -> destination 104.20.1.1
    |
    v
Sao Paulo backbone router
    |
    | BGP route table: shortest path to 104.20.1.1 = Sao Paulo PoP
    v
Cloudflare Sao Paulo PoP handles request
```

All three users hit the same IP address. All three get routed to their nearest PoP. No DNS lookup involved in the routing decision.

Cloudflare, Google (8.8.8.8), Fastly, and Akamai all use Anycast for their global networks. Cloudflare has over 300 PoPs, all announcing the same IP ranges via BGP.

**Why Anycast beats Geo-DNS for first-hop routing:**

- No TTL issues whatsoever. BGP route changes propagate across the internet in seconds, not minutes. If a PoP goes down, BGP withdraws its route announcement and the internet re-routes automatically.
- Routing is based on actual network topology, not an IP geolocation database. No 5% mismatch.
- Automatic failover: when a PoP stops announcing a route, BGP automatically steers all traffic to the next nearest PoP. No health check polling, no Route53 update required.

**Why Anycast is not a complete solution for your application:**

- You cannot control which PoP a specific user hits. Network topology determines it. Load distribution across PoPs can be uneven — a PoP in a densely connected hub may receive disproportionate traffic.
- You cannot guarantee the same user always hits the same PoP — network conditions change.
- Running Anycast requires BGP infrastructure: your own AS number, peering agreements with backbone providers, BGP routers at each PoP. This is complex and expensive. It is practical for Cloudflare-scale companies and very large cloud operators, not for a typical engineering team.

**The practical usage pattern:** most engineering teams use Cloudflare, Fastly, or Akamai as their Anycast-capable front end. All user traffic first hits the nearest Anycast PoP, which handles TLS termination, DDoS scrubbing, and caching. Then the PoP forwards origin traffic to the nearest origin region using Geo-DNS or weighted routing to your actual application servers.

---

### Layer 3: Application-Layer Routing — Smart Forwarding Inside Your Service

Even after Geo-DNS and Anycast correctly route a user to their nearest region, a mismatch problem remains: the user's data may be stored in a different region.

**The concrete problem:** A Shopify merchant opened their store when they lived in London. Their store data — products, orders, customer records — was created in EU-West. Six months later they moved to Toronto. Geo-DNS now routes them to US-East because their IP is in North America. But their store data is still in EU-West. Every read and every write must cross the Atlantic. Latency is high, and the user does not understand why.

**Application-layer routing** solves this. When a request arrives at any regional entry point, the application itself consults a **routing table** — a globally accessible mapping from a key (user ID, shop ID, tenant ID, account ID) to a home region. If the request arrived at the wrong region, the application forwards it to the correct one.

```
Request arrives at US-East API server
    |
    v
+----------------------------------------------+
|   App-Layer Router (US-East)                 |
|                                              |
|  Request context: shop_id = 77234            |
|  Look up shop_id in global routing table     |
|  (routing table stored in Redis or DynamoDB, |
|   replicated to all regions)                 |
|                                              |
|  Result: shop_77234.home_region = EU-West    |
+----------------------------------------------+
    |
    |  Option A: Proxy the request to EU-West (adds ~80ms)
    |  Option B: Return HTTP 307 redirect to eu-west.api.example.com
    v
EU-West API server processes the request
EU-West DB serves the data
```

Shopify uses this pattern: each shop has a designated "primary region," and all writes for that shop are routed to that region. Cloudflare Workers uses a similar approach with their Workers KV store to execute Worker code in the region where the relevant KV data lives.

The routing table itself must be globally accessible and highly available — it is consulted on every request for misrouted users. Options: replicate a small Redis cluster to every region, use DynamoDB Global Tables, or use Cloudflare KV. The table is small (it just maps IDs to region strings) and read-heavy. Because it is read-heavy and the data is small, you can aggressively cache it in local memory on each API server with a short TTL (10-30 seconds). A stale cache entry means a user is briefly routed to the wrong region — acceptable. A missing routing table means you cannot route anyone — not acceptable. Always have a local cache as a fallback.

**Trade-offs:**

| Approach | Latency penalty | Complexity |
|----------|----------------|------------|
| Proxy forward cross-region | +50-150ms one-time | Medium |
| Redirect (307) to correct region | +1 round trip for redirect | Low |
| Migrate data to user's current region | 0ms after migration | High |

For most use cases, proxy forwarding or redirect is acceptable. For latency-sensitive high-value users (e.g., a major enterprise customer connecting consistently from a new region), you would trigger a data migration job to move their shard to the closer region.

**How to decide between proxy and redirect:**

Use a **proxy forward** when you want the cross-region hop to be invisible to the client. The client sends one request, gets one response. The cross-region hop happens inside your infrastructure. This is the better choice for API clients (mobile apps, SDKs) that are not designed to handle HTTP redirects cleanly.

Use an **HTTP 307 redirect** when clients are browsers or well-behaved HTTP clients that handle redirects automatically. The browser sends a request to US-East, receives "307 Temporary Redirect: https://eu-west.api.example.com/..." and automatically follows it. The subsequent request goes directly to EU-West. The benefit: the client now has the correct regional hostname and can use it for future requests, eliminating the forwarding overhead until the next cache expiry.

For Staff-level interviews, explicitly state which approach you are using and why. "We proxy forward at the API gateway layer rather than redirect, because our mobile SDK clients are not designed to follow 307 redirects on API calls, and we do not want to require SDK updates to handle that correctly."

---

### The Full Routing Flow: Two Users, Two Paths

This diagram shows the complete five-layer routing chain for two different users. User A's data is in the same region they connect to — fast, no extra hops. User B's data is in a different region — pays a forwarding penalty.

```
USER A: Browser in Paris, store data in EU-West
=========================================================

Browser (Paris, IP: 195.0.0.1)
    |
    | DNS query: "api.example.com?" (source: 195.0.0.1)
    v
Geo-DNS: 195.x.x.x maps to France -> EU-West
    |
    | Returns: 104.20.1.1 (Anycast IP)
    v
Cloudflare Paris PoP (nearest PoP via Anycast BGP)
    |
    | TLS termination, DDoS filter, cache check
    v
EU-West Regional LB (origin request)
    |
    | Health check: server pool healthy
    v
EU-West API Server (instance #3)
    |
    | App router: shop_id=555 -> home_region=EU-West
    | Data is here. No forward needed.
    v
EU-West PostgreSQL primary
    |
    v
Response: ~28ms total round-trip to Paris browser


USER B: Browser in Toronto, store data in EU-West
=========================================================

Browser (Toronto, IP: 142.0.0.1)
    |
    | DNS query: "api.example.com?" (source: 142.0.0.1)
    v
Geo-DNS: 142.x.x.x maps to Canada -> US-East
    |
    | Returns: 104.20.1.1 (Anycast IP, Toronto nearest PoP)
    v
Cloudflare Toronto PoP (nearest PoP via Anycast BGP)
    |
    | TLS termination, cache check (miss)
    v
US-East Regional LB (origin request)
    |
    v
US-East API Server (instance #7)
    |
    | App router: shop_id=999 -> home_region=EU-West
    | Data is NOT here. Forward to EU-West.
    v
[Cross-region forward: US-East -> EU-West, ~80ms]
    |
    v
EU-West API Server (instance #2)
    |
    v
EU-West PostgreSQL primary
    |
    v
Response: ~135ms total round-trip to Toronto browser
```

User A gets fast, local service. User B pays a cross-region penalty on every non-cached request. Over time, if User B consistently generates high traffic volume from Toronto, an automated job would trigger a shard migration — physically moving shop_999's data from EU-West to US-East — after which User B's requests would look like User A's.

### Summary: Which Routing Mechanism for Which Problem?

A common interview mistake is proposing only one routing mechanism and assuming it handles everything. Real systems layer multiple mechanisms, each addressing the gaps left by the previous one.

| Routing Mechanism | What it solves | What it does NOT solve |
|-------------------|---------------|----------------------|
| Geo-DNS | Routes most users to nearest region at DNS time | TTL staleness, IP inaccuracy, no health awareness |
| Geo-DNS + Health Checks | Automatic failover on full region outage | TTL delay (30-60s), misses latency degradation |
| Anycast | Network-level routing, no TTL, auto-failover | Uneven load distribution, no app-layer awareness |
| Latency-based routing | Routes away from slow regions, not just dead ones | Still has DNS TTL delay; needs external latency probes |
| App-layer routing | Handles user-data-region mismatch correctly | Adds cross-region hop latency for forwarded requests |

In a production Staff-level design, you would typically combine: Anycast at the edge (Cloudflare or Fastly), Geo-DNS + health checks for regional origin routing, and application-layer routing for data-locality mismatches. Each layer handles what the layer above it cannot.

---

## Section 2: User Affinity and Sticky Sessions

### The Analogy: Bank ATM vs. Your Personal Accountant

An ATM is **stateless**. You insert your card at any ATM in any country and get your balance. The ATM does not remember previous transactions you ran at other ATMs. Any ATM can serve you because all the state (your balance, transaction history) lives in the bank's central database, not in the ATM.

Your personal accountant is **stateful**. They have your full financial history, ongoing tax strategy, and current year's work-in-progress in their head and on their desk. If they are unavailable, you cannot just walk into any accountant's office and continue mid-project. The context is pinned to that specific person.

Your services have the same distinction. **Stateless services** — most REST APIs that read from a database — can be served by any instance in any region. The state lives in the database, not in the server. These are easy to scale globally. **Stateful services** — a live WebSocket connection maintaining a user's game state in server memory, an ongoing streaming video transcoding job, a multi-step checkout flow with in-memory cart state — require the same server (or at minimum the same region) to maintain session context across multiple interactions.

---

### Three Ways to Implement Sticky Routing

**User affinity** (also called **sticky sessions**) is the technique of routing the same user to the same region consistently across all their requests.

**Method 1: Hash-based affinity.** Compute a deterministic hash of the user's identifier and map the result to a region.

```
region_index = hash(user_id) % num_regions
user_id=12345 -> hash=7890123 -> 7890123 % 3 = 0 -> EU-West
user_id=99999 -> hash=1234567 -> 1234567 % 3 = 1 -> US-East
user_id=55555 -> hash=4567890 -> 4567890 % 3 = 2 -> AP-Tokyo
```

Every time user_id=12345 makes a request from anywhere in the world, the hash deterministically maps them to EU-West. No lookup needed. No state stored. This is fast and requires zero coordination infrastructure. The downside: you cannot reassign a user to a different region without changing the hash function or the number of regions, which remaps all users simultaneously.

**Method 2: Cookie-based affinity.** On a user's first request, assign them a region and set a cookie (`X-Assigned-Region: eu-west`). Your load balancer or API gateway reads this cookie on every subsequent request and routes accordingly.

```
First request (no cookie):
    |
    v
LB: no region cookie found
    |
    | Assign region based on geo: EU-West
    | Set cookie: X-Assigned-Region=eu-west; Max-Age=86400
    v
EU-West handles request

Subsequent requests (cookie present):
    |
    v
LB: reads X-Assigned-Region=eu-west
    |
    | Route to EU-West regardless of user's current IP
    v
EU-West handles request
```

Cookie-based affinity lets you reassign a user (issue a new cookie with a different region) and supports fine-grained control. The downside: if the user switches devices or clears cookies, they lose their region assignment and get reassigned.

**Method 3: IP-based affinity.** Route based on source IP. Simple to implement at the load balancer level. Unreliable because users switch networks (home, office, mobile data, hotel WiFi all have different IPs).

| Method | Deterministic | Survives network change | Manually reassignable | Complexity |
|--------|--------------|------------------------|----------------------|------------|
| Hash-based | Yes | Yes | Difficult | Low |
| Cookie-based | No (loses on clear) | No | Yes (new cookie) | Medium |
| IP-based | Per IP only | No | No | Very low |

---

### The Session Handoff Problem: What Happens When the Sticky Region Fails

Sticky routing only works until the region it pins the user to fails. Then you face a hard question: the user's session state was in that region's memory, and it is now gone. What do you do?

**Scenario:** A user has been playing an online multiplayer game for 45 minutes. Their game state — character position, inventory, current match scores, team composition, active power-ups — is held in US-East server memory. At T=2:47 AM, US-East fails catastrophically.

**Option 1: Lose the state.** The simplest response: tell the user "your session was lost, please reconnect." They restart from scratch. This is technically trivial to implement but destroys user trust in a paid gaming service. Only acceptable for truly ephemeral sessions (e.g., a session for browsing a product catalog, where nothing irreplaceable is in memory).

**Option 2: Checkpoint the state periodically.** Every N seconds, serialize the in-memory game state to a durable, geographically replicated store (Redis with sync replication, DynamoDB Global Tables). On failover, the new region loads the last checkpoint.

```
US-East game server memory state:
    -> every 5 seconds: serialize game_state, write to Redis
    -> Redis replicates synchronously to EU-West Redis replica
    -> US-East fails at T=2:47:03
    -> Last successful checkpoint written at T=2:47:00
    -> EU-West loads checkpoint: 3 seconds of game state lost
    -> User reconnects to EU-West, resumes from checkpoint
    -> Total downtime experienced by user: ~15-20 seconds
       (detection + DNS propagation + reconnect time)
```

This is the standard approach for most interactive real-time services. The data loss window (N seconds) is the RPO for this design. You tune N based on acceptable user experience.

**Option 3: Continuously replicated in-memory state.** Keep the in-memory state synchronized to a replica in another region with near-zero lag. On failover, the replica is instantly current. Zero data loss. This requires a dedicated state replication channel, extremely high bandwidth, and careful consistency management. It is used in financial trading systems and real-time bidding platforms where microseconds of lost state translate directly to money. It is not practical for a game checkpoint scenario.

For Staff-level interviews, do not just say "we checkpoint state." Quantify the trade-off: "We accept up to 5 seconds of session state loss on regional failover. We checkpoint to Redis every 5 seconds with synchronous replication to EU-West. Failover recovery time is approximately 15-20 seconds from failure detection. This is acceptable for a gaming product but would not be acceptable for a real-time trading platform."

### The Trade-off Table: Stateless vs. Stateful Region Design

One of the most important architectural decisions in a multi-region system is how much state you allow to live outside a database — in memory, in a local cache, in a session structure. The more in-memory state you have, the faster your service runs. The more in-memory state you have, the harder failover becomes.

| Design | Failover complexity | Latency | Typical use case |
|--------|--------------------|---------|--------------------|
| Fully stateless (all state in DB) | Trivial: just route to new region | Higher (DB round-trips per request) | REST APIs, read-heavy services |
| Checkpointed state (in-memory + periodic flush) | Medium: load last checkpoint | Medium | Games, chat, collaborative editing |
| Replicated in-memory state | High: maintain live replica | Lower (in-memory reads) | Real-time trading, live auctions |
| Fully in-memory (no persistence) | Impossible: state is lost on failure | Lowest | Caches, ephemeral computation |

The general principle: **push state into your database whenever the performance penalty is acceptable**. In-memory state that is not replicated is a failover liability. If you do maintain in-memory state, checkpoint it on a schedule that matches your acceptable RPO, and always replicate the checkpoint store to at least one other region before it can be considered durable.

---

## Section 3: Failure Scenarios — What Actually Goes Wrong

### The Mental Model: Failures Are Partial, Gradual, and Confusing

The most dangerous misconception about regional failures is that regions are either completely up or completely down — binary states. In production, almost every regional failure is **partial, gradual, and ambiguous**. A region running at 60% capacity is harder to handle than a region that is completely dead, because the system cannot cleanly decide whether to fail over.

Think of it like a colleague who is "kind of sick." They are not absent (so you cannot officially reassign their work), but they are not performing at full speed (so the team is suffering). You do not know whether to give them lighter tasks or just pull them off the project completely. The uncertainty is what makes it hard.

The hardest production incidents are not "US-East is completely down." Those are obvious — all metrics flatline, alarms fire immediately, the on-call engineer wakes up to a cascade of alerts. The hardest incidents are partial degradation: latency slightly high, error rate slightly elevated, health checks flapping between pass and fail.

---

### Failure Scenario 1: Full Region Isolation (The Hard Partition)

**What happens:** A network fiber cut, a cloud provider backbone failure, or a BGP misconfiguration causes a complete hard partition. US-East becomes totally unreachable from the outside world and from other regions. The servers inside US-East still run — they can talk to each other — but no traffic can enter or leave. It is as if someone put the entire data center inside a submarine and cut the radio.

**What active-passive systems must do:**

The passive region (EU-West) detects that US-East is unreachable via health checks and begins failover. The goal: promote EU-West to primary so it can accept writes.

The serious danger here is **split-brain**: US-East is isolated but still running internally. If it was a primary accepting writes before the partition, it might still be processing in-flight requests that arrived just before the cut. If EU-West is now also promoted as primary, both regions are simultaneously accepting writes to the same logical dataset. When the partition heals, you have two diverged versions of the truth.

**STONITH** — "Shoot The Other Node In The Head" — is the principle for preventing split-brain. Before EU-West can be safely promoted, the failover system must guarantee US-East cannot accept any more writes. Implementation options:

- A separate out-of-band control channel (different physical network path) can reach US-East's database and revoke write credentials.
- US-East's database requires quorum confirmation from EU-West before committing writes — a confirmation it cannot get because the partition has severed connectivity. Writes in US-East start failing automatically.

```
Normal active-passive state:
+----------+       replication       +----------+
| US-East  | --------------------->  | EU-West  |
| PRIMARY  |   (replica lag < 1s)    | STANDBY  |
+----------+                         +----------+

Hard partition event at T=02:47:
+----------+  //PARTITION// +----------+
| US-East  |  X  X  X  X   | EU-West  |
| PRIMARY  |  unreachable   | STANDBY  |
+----------+                +----------+

T=02:47:30: EU-West: health checks to US-East failing (1 of 3)
T=02:48:00: EU-West: health checks to US-East failing (2 of 3)
T=02:48:30: EU-West: health checks to US-East failing (3 of 3)
T=02:48:30: Automated failover begins
T=02:48:31: Fence US-East: revoke US-East DB write credentials
T=02:48:35: Verify US-East cannot write (test write returns error)
T=02:48:36: Promote EU-West to PRIMARY
T=02:48:40: Update routing: all traffic -> EU-West

Final state:
+----------+  //PARTITION// +----------+
| US-East  |  X  X  X  X   | EU-West  |
| FENCED   |                | PRIMARY  |
+----------+                +----------+
```

**Active vs. passive failover decisions:**

| Property | Automatic Failover | Manual Failover |
|---------|-------------------|----------------|
| Speed to recover | Seconds to 2 minutes | 5-20 minutes (human on-call) |
| Risk of false positive | Higher (flapping health checks) | Lower (human judgment) |
| Split-brain risk | Present (needs careful fencing) | Lower (human double-checks) |
| Read failover safety | High | High |
| Write failover safety | Medium | High |

Industry consensus at Staff level: automatic failover is appropriate for **read traffic** (route reads away from an unhealthy region automatically, no split-brain risk). For **write failover**, prefer either manual approval or a dead-man's switch: the system proposes a write failover, sets a 2-minute timer, and executes automatically unless a human cancels. This gives the human a safety window without requiring urgent decision-making under extreme time pressure.

---

### Failure Scenario 2: Partial Network Partition (The Hardest Case)

**What happens:** US-East and EU-West have a degraded network link. They can communicate, but with 40% packet loss and latency of 500ms instead of the normal 80ms. Health checks sometimes succeed and sometimes time out. The system is genuinely unable to determine with confidence whether US-East should be considered healthy.

**The flapping problem — how automated failover makes things worse:**

```
T+00s: EU-West health check to US-East -> TIMEOUT (fail)
       -> Automated failover TRIGGERS
T+30s: EU-West health check to US-East -> 200 OK (pass)
       -> Automated failback TRIGGERS
T+60s: EU-West health check to US-East -> TIMEOUT (fail)
       -> Automated failover TRIGGERS AGAIN
T+90s: EU-West health check to US-East -> 200 OK (pass)
       -> Automated failback TRIGGERS AGAIN
```

Each failover-failback cycle drops active connections, requires DNS propagation, and disrupts in-flight requests. A system flapping between regions every 30-60 seconds is in a worse state than one that has simply made a clean failover decision and stayed there.

**Solutions:**

- **Require N consecutive failures.** Configure: "Only trigger failover after 3 consecutive health check failures, each 30 seconds apart." This means the system must be degraded for at least 90 seconds before any action is taken. This eliminates most transient failures from triggering unnecessary failovers.
- **Circuit breaker with hysteresis.** A circuit breaker should not close (return to healthy state) after a single passing health check. Require a "sustained healthy" window — for example, 5 consecutive passing checks — before declaring the region recovered. This prevents the T+30 -> T+60 flip in the example above.
- **Human approval for write failover during ambiguity.** When health checks are flapping (alternating between pass and fail), automated systems cannot make a good decision. Page the on-call engineer with full context: current error rate, replica lag, affected user count. Let the human decide.

**What degrades first during a partial partition, in order:**

1. Cross-region replica reads: slow, high error rate, unreliable. Users getting stale reads or timeouts.
2. Cross-region write forwarding (read-local/write-central pattern): write latency spikes to 500ms+ with frequent timeouts. Users experience slow saves.
3. Health check consensus: quorum mechanisms (used by databases like etcd, ZooKeeper) may fail to achieve quorum. Automated cluster management stalls.
4. Eventually: the system is considered "up" by some measurement paths and "down" by others, depending on which network path the probe takes. Monitoring dashboards show contradictory data.

**Real-world reference:** AWS had multiple partial outages of us-east-1 between 2020 and 2022 where specific services (EC2 instance metadata, EBS, ELB) were degraded but not fully down. Some customers' automated failover systems triggered unnecessarily, causing cascading problems — their healthy applications in other regions were disrupted by the failover machinery itself. Customers who relied on manual failover with detailed runbooks and good observability handled these incidents more gracefully.

---

### Failure Scenario 3: Slow or Degraded Region (The Invisible Failure)

**What it looks like:** US-East is passing every health check. The `/health` endpoint responds in 8ms with a 200 OK. But real user-facing p99 latency has spiked from 50ms to 2,000ms. The cause: a hot shard in DynamoDB is throttling writes, causing a queue backup that propagates through the entire request path.

**Why standard tooling misses this:**

Health checks probe a synthetic endpoint that does not touch the hot database shard. They pass. Geo-DNS sees a healthy region and continues routing users there. Your load balancer sees healthy instances and continues distributing traffic. Zero automated systems respond.

The only way to catch this is **SLO-based observability**: monitoring actual user-facing latency (p50, p95, p99) from production traffic, not from synthetic probes. Your dashboards need to show real percentiles for real user requests, with alert thresholds below your SLO targets.

**Automated responses:**

- **Latency-based routing (Route53):** Route53 supports a "Latency Routing" policy that measures actual latency from AWS vantage points to your regional endpoints and routes users to the fastest-responding region. This detects slowness even when health checks pass, and routes users away from the slow region.
- **Cloudflare Argo Smart Routing:** Cloudflare continuously measures latency across their global network and automatically routes each request through the fastest available path in real time. It does not wait for health checks.
- **SLO-triggered circuit breaker:** Configure your monitoring system to detect when p99 latency exceeds a threshold (e.g., 500ms) sustained for 2 minutes, and automatically invoke the same gradual traffic-shift procedure as a health-check failover.

**The gradual shedding strategy:**

A hard binary failover (suddenly move 100% of traffic from US-East to EU-West) can overwhelm EU-West with a sudden spike. Instead, gradually shift a percentage of new connections away from the degraded region:

```
T=0:   US-East p99 = 2000ms. Begin shedding.
       Route53 weighted: US-East=90%, EU-West=10%

T=2m:  US-East still degraded.
       Route53 weighted: US-East=75%, EU-West=25%

T=5m:  US-East still degraded.
       Route53 weighted: US-East=50%, EU-West=50%

T=10m: US-East still degraded.
       Route53 weighted: US-East=0%, EU-West=100%
       (full failover complete)

T=15m: US-East recovers (hot shard issue resolved).
       Gradual ramp BACK: 10% -> 25% -> 50% -> 100%
```

The benefit: EU-West absorbs US-East's traffic gradually, giving it time to scale horizontally (add instances) before it reaches its full load. The recovery ramp-back prevents a new surge when US-East comes back online.

---

### Failure Scenario 4: Control Plane vs. Data Plane Failures

**The key distinction you must own at Staff level:**

The **data plane** is every system that directly handles user requests: API servers, databases, caches, message queues. When the data plane works, users get successful responses.

The **control plane** is every system that coordinates and manages the data plane: Kubernetes (orchestration), Consul or etcd (service discovery), configuration management systems (AppConfig, Vault), feature flag services (LaunchDarkly), deployment pipelines (Spinnaker, Argo CD), and monitoring/alerting infrastructure.

Think of it as the factory floor versus the factory management office. The floor workers (data plane) actually build the product. The management office (control plane) schedules shifts, orders materials, and routes work. If the office burns down, the floor workers might keep going for a while on their existing instructions — but they will eventually run out of direction, materials, and coordination.

**Why control plane failures are uniquely dangerous in multi-region systems:**

A control plane failure at the wrong time is worse than a data plane failure because it prevents you from responding to any other failure. Specifically:

- **Service discovery failure:** instances register with a service registry (Consul, Kubernetes DNS) so other services can find them. If the registry fails, new instances cannot register and existing services cannot discover them. A healthy API server cannot reach a healthy database because neither can find the other.
- **Config management failure:** you cannot update routing rules, change feature flags, adjust rate limits, or push any configuration change to running services. You are frozen in whatever state the system was in when config management went down.
- **Deployment pipeline failure:** you cannot push a hotfix or roll back a bad deploy — at exactly the moment a bad deploy may have caused the incident you are trying to fix.

**Real example: AWS Kinesis Control Plane Outage, November 2020**

AWS Kinesis's control plane experienced a major incident. The symptom: customers could not call `DescribeStream` or retrieve connection metadata for their Kinesis streams. The downstream cascade was severe and widespread:

- AWS Cognito (which uses Kinesis internally for its own event logging) degraded and began returning errors to customers trying to authenticate.
- Amazon CloudWatch Logs degraded (it uses Kinesis internally for log ingestion). Customers lost observability into their own systems at the exact moment they needed it most.
- AWS CloudFormation degraded (it uses CloudWatch and Kinesis). Infrastructure automation stalled.

The actual Kinesis data plane — actual message delivery through streams — was mostly functioning. Streams that were already connected and streaming continued to work. But because the control plane (the API that describes stream configuration, returns connection endpoints, and manages stream state) was broken, every service that bootstrapped against Kinesis's API at startup could not initialize. Services that tried to reconnect after any disruption could not get back up.

The lesson: control plane failures cascade invisibly into data plane failures because so much of the data plane depends on the control plane for initialization and ongoing coordination.

**Design principles for control plane resilience:**

- **Data plane must function without the control plane, at least temporarily.** API servers should cache their last-known configuration locally to disk. If the config service is unreachable, they continue operating with the cached version rather than refusing to serve traffic.
- **Feature flag clients must fail safely.** If the feature flag service (LaunchDarkly, etc.) is unreachable, clients should continue with the last cached flag state, or fall back to a hardcoded safe default.
- **Control plane infrastructure needs its own geographic redundancy.** This is doubly important: if your control plane has a single-region deployment and that region fails, you lose the ability to manage your data plane globally.
- **Break-glass procedures are mandatory.** Document: how do you manually update a load balancer routing rule if Kubernetes is down? How do you manually update a database connection string if the config system is down? These procedures must exist, be written down, be tested regularly, and be executable by any senior on-call engineer without help from the tooling that is currently broken.

---

### Failure Scenario 5: The Cascading Cross-Region Failure

**The anatomy of a global cascade:**

This is the failure mode that keeps infrastructure architects up at night. A regional failure in one zone does not stay contained — it propagates to healthy regions and takes them down too.

```
INITIAL STATE: Each region at 60% of peak capacity
+----------+    +----------+    +----------+
| US-East  |    | EU-West  |    | AP-Tokyo |
|  60% cap |    |  60% cap |    |  60% cap |
+----------+    +----------+    +----------+

STEP 1: Marketing campaign goes viral.
        US traffic surges. US-East hits 110% capacity.
        p99 latency: 50ms -> 3000ms.
+----------+    +----------+    +----------+
| US-East  |    | EU-West  |    | AP-Tokyo |
| 110% OVER|    |  60% cap |    |  60% cap |
+----------+    +----------+    +----------+

STEP 2: Latency-based routing detects US-East slowness.
        Starts routing 50% of US traffic to EU-West.
+----------+    +----------+    +----------+
| US-East  |    | EU-West  |    | AP-Tokyo |
| degraded |    |60%EU+50% |    |  60% cap |
|          | -> |US traffic|    |          |
+----------+    | = ~110%  |    +----------+
                | OVERLOAD |
                +----------+

STEP 3: EU-West overloaded. Latency-based routing detects.
        Reroutes EU traffic to AP-Tokyo.
+----------+    +----------+    +----------+
| US-East  |    | EU-West  |    | AP-Tokyo |
| degraded |    | degraded |    |60%AP     |
|          | -> |          | -> |+EU traffic|
+----------+    +----------+    | = ~130%+ |
                                | OVERLOAD |
                                +----------+

RESULT: Global outage. All three regions degraded.
        Zero regions can serve any traffic adequately.
```

**Why this cascade was allowed to happen:**

- Each region was sized for its own normal traffic peak, not for absorbing overflow from neighboring regions.
- The latency-based routing did not check the target region's capacity before redirecting traffic.
- A retry storm amplified the problem: when US-East became slow, clients began retrying failed requests, doubling the effective traffic being generated.

**Prevention strategy 1: Size regions to absorb overflow.** Each region should be able to handle 150-200% of its normal peak traffic. You are paying for capacity you normally do not use. Frame this to your finance team as insurance: the cost of idle capacity is far lower than the revenue lost in a global cascade outage.

**Prevention strategy 2: Capacity-aware routing.** Before routing overflow traffic to a target region, check that region's current load. If EU-West is already at 80% CPU, do not route US-East's overflow there. Distribute the overflow proportionally to available headroom across all regions.

**Prevention strategy 3: Shed before failing over.** When a region becomes overloaded, the first action should be internal load shedding — drop or defer non-critical traffic to free capacity for critical paths — rather than immediately pushing the problem to another region.

```
US-East overloaded: 110% capacity
    |
    v
+--------------------------------------------+
|  Overload Response (in order):             |
|                                            |
|  Step 1: Shed non-critical traffic         |
|    - Background analytics: DROP            |
|    - Recommendation refreshes: DROP        |
|    - Non-priority batch jobs: DEFER        |
|    -> US-East now at ~90% (stable)         |
|                                            |
|  Step 2: If still > 95% after shedding:   |
|    Check capacity headroom in EU-West,     |
|    AP-Tokyo before redirecting             |
|    EU-West headroom: 40% free -> can take  |
|      ~35% of US overflow                   |
|    AP-Tokyo headroom: 40% free -> can take |
|      ~35% of US overflow                   |
|    Route 35% overflow to each.             |
|    Both neighbors stay under 95%.          |
+--------------------------------------------+
```

**Prevention strategy 4: Test your failover paths under load.** Netflix's Chaos Engineering program injects failures and failovers in production continuously, specifically to validate that failover paths work under realistic traffic conditions. If you only test failover during low-traffic periods, you will discover on the worst possible day that your failover paths cannot actually handle the load they would receive in a real incident. Run your game-day drills during peak hours.

---

## Section 4: Recovery Patterns

### The Runbook: Your Most Important Multi-Region Asset

A **runbook** is a written, step-by-step procedure for handling a specific, well-defined operational scenario. For multi-region systems, regional failover runbooks are the single most important operational artifact you can create. They transform a high-pressure, middle-of-the-night emergency into a sequence of mechanical steps that any trained on-call engineer can execute.

Good runbooks are written at a level of detail that a senior engineer who has never personally executed this procedure can follow successfully without making judgment calls. If a step requires judgment, the runbook should define what information to gather and what decision criteria to use.

**A complete regional failover runbook outline:**

```
RUNBOOK: US-East Primary Regional Failover
==========================================
Owner: Platform Reliability Team
Last tested: [game-day date]
Estimated execution time: 8-15 minutes

PRE-REQUISITES:
- You are the primary on-call engineer
- A second engineer is paged and available as backup
- You have confirmed this is NOT a scheduled maintenance window

STEP 1: VERIFY THE FAILURE IS REAL (do not skip)
  a. Are Route53 health checks failing for US-East? (3+ consecutive)
     Check: Route53 console -> Health Checks -> us-east-primary
  b. Are external probes failing? (Datadog synthetic monitor,
     PagerDuty webhook, StatusCake)
  c. Is user-facing error rate above SLO threshold?
     Check: Grafana -> SLO dashboard -> US-East error rate
  d. Is this a new deployment that might explain degradation?
     Check: deployment log for past 30 minutes
  If uncertain: page secondary on-call, do NOT proceed alone.

STEP 2: CLASSIFY THE FAILURE
  Full outage (0% traffic getting through)
    -> Proceed to Step 3 immediately
  Partial degradation (health checks flapping or latency elevated)
    -> Begin gradual traffic shift (see RUNBOOK: Gradual Shedding)
    -> Page secondary before proceeding to write failover

STEP 3: CHECK REPLICA LAG AT TIME OF FAILOVER DECISION
  Run: psql $EU_WEST_DB -c "SELECT * FROM replication_lag_view;"
  Acceptable: replica lag < 30 seconds
  Unacceptable: replica lag > 30 seconds
    -> Page data team lead, document lag, get explicit approval before
       proceeding to write failover

STEP 4: FENCE US-EAST (prevent split-brain)
  Run: ./ops/fence_region.sh us-east
  Expected output: "us-east successfully fenced. Writes disabled."
  Verify: run a test write, confirm it returns "region fenced" error
  If fence script fails: DO NOT promote EU-West. Page oncall escalation.

STEP 5: PROMOTE EU-WEST TO PRIMARY
  Run: ./ops/promote_primary.sh eu-west
  Wait for: "eu-west is now PRIMARY. Accepting writes."
  Estimated time: 30-90 seconds

STEP 6: UPDATE ROUTING RULES
  Run: ./ops/update_routing.sh --primary eu-west --remove us-east
  Verify: DNS query from external resolver returns EU-West IP
  Wait: 60 seconds for TTL propagation

STEP 7: VERIFY TRAFFIC IS FLOWING CORRECTLY
  Check: EU-West ingress traffic increased (Grafana -> EU-West traffic)
  Check: EU-West p99 latency is within SLO
  Check: EU-West error rate is within SLO
  Check: No unexpected replication errors in EU-West DB logs

STEP 8: COMMUNICATE
  - Post to #incidents: "US-East failover complete. EU-West is primary.
    Impact window: [T-start] to [T-end]. Replica lag at decision: Xs."
  - Update status page: "US-East service degradation - resolved"
  - If user-visible SLO was missed: file incident report, page VP Eng
```

At Google, runbooks are a required deliverable for any production service before it passes launch review. The existence of a well-tested runbook signals operational maturity. At a Staff-level interview, saying "I maintain runbooks with documented RPO/RTO commitments and hold quarterly game-day exercises where we practice the failover procedure on a staging environment" distinguishes you from candidates who give vague answers about "automated failover."

---

### Data Reconciliation After Split-Brain Recovery

When a network partition heals and you discover both sides were writing independently — despite your best fencing efforts — you have **diverged state**. Both regions hold different versions of the same records. You must determine which version is authoritative and bring both sides back into agreement.

This process is slow, error-prone, and expensive. It is the strongest possible argument for investing heavily in split-brain prevention. But when it happens, here is the structured recovery process:

**Step 1: Identify the divergence point.** Both databases maintain a transaction log (WAL in PostgreSQL, binary log in MySQL, change feed in DynamoDB). Find the last transaction that appears in BOTH logs — the last common ancestor before the partition diverged the two histories. Every transaction after that point is potentially in conflict.

**Step 2: Enumerate which records have conflicts.** Some records were modified only on one side (no conflict — apply the change to the other side). Some were modified on both sides (conflict — requires resolution). Automated tools (custom scripts against the transaction logs, or CRDTs in eventual consistency systems) can enumerate conflicts programmatically.

**Step 3: Resolve conflicts by data type:**

| Data type | Resolution strategy | Risk |
|-----------|-------------------|------|
| User profile fields (name, address, bio) | Last write wins (higher timestamp) | Low: minor profile version loss |
| Counter fields (likes, views, inventory) | Apply both deltas: final = base + delta_A + delta_B | Medium: can create impossible values |
| Financial transaction records | Manual review — never auto-resolve | High: cannot lose or duplicate money |
| Soft-deleted records | Delete wins (if either side deleted, it stays deleted) | Low |
| Session or ephemeral state | Discard both (force re-login) | Medium: user inconvenience |

**Step 4: Apply the winner's changes to the loser region.** Replay the winning transactions on top of the loser's current state, using the conflict-resolved values for any conflicted records.

**Step 5: Audit critical records.** For any financial, legal, or compliance-sensitive records in the conflicted set: manual review is mandatory. Automated tools cannot safely resolve these. Document every decision made and every record that was altered.

**Step 6: Notify affected users if necessary.** If a user's data was incorrectly reverted or if a transaction appears to have been lost, they must be informed. In financial systems, every transaction must be accounted for — there is no "acceptable loss."

**What split-brain recovery looks like at scale:**

To make this concrete: imagine a mid-size e-commerce platform with 10 million users, where a 12-minute partition caused both US-East and EU-West to independently accept writes. During those 12 minutes:

- Approximately 1.4 million requests were processed (based on typical traffic patterns)
- Perhaps 80,000 write operations modified user records, orders, or inventory
- Perhaps 2,000 of those write operations touched the same record on both sides (true conflicts)
- 15 of those conflicted records involve financial data (order cancellations, refunds issued on both sides)

The automated reconciliation tool handles the 79,985 non-conflicted writes in 20 minutes. The 15 financial conflicts require two engineers and a data team member to manually review, cross-reference with payment processor records, and manually correct. This takes 4 hours and results in 3 customer support tickets from users who noticed their refund state was wrong.

That is the real cost of split-brain: not just the engineering time, but the customer-visible data inconsistencies and the support burden.

The cost of this process — in engineering hours, in customer impact risk, in the probability of getting a resolution wrong — is measured in days to weeks for large-scale splits. Prevention through fencing, quorum requirements, and conservative failover procedures is worth any reasonable engineering investment.

---

### Graceful Degradation During Regional Failure

Regional failures do not require every feature to go down. They require your **critical path** to keep working while **non-critical features degrade gracefully** — serving stale data, simplified responses, or explicit "temporarily unavailable" messages.

The restaurant analogy: the kitchen has a gas leak and half the stoves are off. The restaurant does not close. They cross half the menu off the chalkboard, apologize for the limited options, and keep serving the dishes they can make. Revenue is reduced, but it is not zero.

**Tagging your API surface by criticality:**

| Feature | Criticality | Degraded behavior |
|---------|------------|-------------------|
| User authentication / login | Critical | Must work — no degradation |
| Read account data, order history | Critical | Serve from local replica, may be 30s stale |
| Submit new order / write | Critical | Must work — failover to healthy region |
| Payment processing | Critical | Must work — no degradation |
| Product recommendations | Non-critical | Serve from 1-hour cache, or return empty list |
| Reviews and ratings | Non-critical | Return last cached snapshot or empty |
| Personalized homepage | Non-critical | Return non-personalized default layout |
| Real-time analytics (view counts) | Non-critical | Return stale or suppress entirely |
| Background notification delivery | Non-critical | Queue and deliver when healthy |

**Implementation pattern — degraded mode flag:**

During a regional incident, your system raises a `DEGRADED_MODE` flag (via a feature flag system or a shared config cache). Every API handler checks this flag before calling non-critical downstream services:

```
GET /homepage
  -> fetch user profile  (critical, always call)
  -> if NOT degraded_mode:
       fetch personalized recommendations  (non-critical)
     else:
       return [] for recommendations, log as degraded
  -> if NOT degraded_mode:
       fetch real-time trending items  (non-critical)
     else:
       return cached static list
  -> render homepage
```

This is exactly what Netflix tests with Chaos Monkey: randomly terminate service instances (recommendations, reviews, personalization) and verify that a user can still browse the catalog and press play on a movie. If removing any single non-critical service causes the core product to fail, that is a bug — the core product has an undeclared critical dependency that must be fixed.

---

### Pulling It All Together: Seven Questions Every Staff Engineer Must Answer

A Staff-level engineer thinking about a multi-region system does not reason about any single layer in isolation. They reason about the entire system under realistic failure conditions before the system is built, and they write down the answers.

Here are the seven questions that should drive every multi-region design review:

1. **How does traffic reach the correct region under normal conditions?** Which combination of Geo-DNS, Anycast, and application-layer routing is appropriate for this product's latency requirements and data residency constraints?

2. **What is the automatic failover path for each region?** If US-East fails, what exactly happens? Which automated systems trigger? In what sequence? What is the expected time from failure onset to traffic fully redirected?

3. **What are the RPO and RTO commitments, and are they acceptable?** Replica lag at time of failover determines RPO. Detection + promotion + routing update times determine RTO. "As fast as possible" is not an answer. "RPO < 30 seconds, RTO < 5 minutes" is an answer.

4. **How does the system behave during a partial degradation, not a full outage?** Does it flap? Does it handle gradual traffic shedding? Is there a human-in-the-loop for write failover decisions during ambiguity?

5. **Can the data plane operate if the control plane fails?** What happens if Kubernetes, Consul, or the config management system goes down? Is there a break-glass procedure?

6. **Is each region sized to absorb overflow from at least one other region?** Is there a capacity-aware routing rule that prevents cascade failures?

7. **Are runbooks written, tested, and rehearsed?** When was the last game-day drill? What was the measured RTO during the drill? What broke during the drill and was subsequently fixed?

Engineers who can answer all seven questions — with specific numbers, named technologies, and explicit trade-offs — are the ones trusted to own multi-region systems at Staff level and above.

---

### Testing Your Multi-Region Failover: Game Days

Writing a runbook is not enough. A runbook that has never been executed is a hypothesis, not a procedure. The only way to validate that your failover works — that the fencing script actually fences, that promotion actually completes in under 90 seconds, that routing updates propagate correctly — is to execute it under realistic conditions.

**Game days** (also called chaos engineering exercises or disaster recovery drills) are scheduled events where you intentionally trigger a regional failover in a controlled environment while engineering and operations teams watch in real time.

**A game day structure for multi-region failover:**

```
GAME DAY: Regional Failover Drill
Date: [scheduled quarterly]
Duration: 2 hours
Environment: staging (with production traffic mirror)
Participants: SRE team, database team, network team, on-call engineer

PHASE 1 (30 min): Briefing
  - Review the runbook together
  - Assign roles (executor, observer, scribe)
  - Set up monitoring screens
  - Confirm rollback procedure is ready

PHASE 2 (30 min): Execute failover
  - Simulate US-East failure (block health check endpoint)
  - Follow runbook steps exactly as written
  - Scribe records actual time for each step
  - Observers note anything unexpected

PHASE 3 (20 min): Validate
  - Is traffic flowing to failover region?
  - Are SLOs met in failover region?
  - What is actual measured RTO?
  - Any unexpected errors or gaps in runbook?

PHASE 4 (20 min): Fail back
  - Restore US-East
  - Re-promote US-East to primary
  - Verify replication re-established

PHASE 5 (20 min): Retrospective
  - Document actual vs. expected RTO
  - List every step where something was unclear or wrong
  - Assign follow-up tasks to fix gaps
```

**What game days routinely reveal:**

- Steps in the runbook that reference tools or scripts that have changed since the runbook was written
- Permissions that were removed from the on-call IAM role during a security audit, preventing a required step
- Replica lag that is higher than expected because a background job was not accounted for
- DNS propagation that takes 3 minutes instead of 1 minute because the upstream ISP resolver has a longer TTL cache than expected
- Monitoring gaps: certain metrics do not flow from the failover region, leaving operators blind during the critical window

Netflix runs Chaos Monkey in production continuously, not just in drills. At smaller scale, quarterly game days with staging environment failovers are the standard minimum. The goal is to have every engineer on the on-call rotation execute a full regional failover at least once before they face a real incident at 3 AM.

One pattern seen repeatedly in mid-level engineers is designing the routing and replication correctly for normal operation, then treating failure handling as an afterthought ("we'll add failover later"). At Staff level, this is considered incomplete work.

The reason is not just engineering rigor. It is business reality. When a regional failure happens — and it will, given enough time — the system's behavior under that failure is as important to users as its behavior under normal conditions. An outage that could have been a 2-minute blip but turned into a 90-minute cascade because there was no failover plan is an engineering failure, not just an operations failure.

The Staff-level mindset is: **the failure path must be designed as carefully as the happy path.** For every region-to-region link in your architecture diagram, ask: "What happens if this link fails? What happens if it becomes slow? What happens if it works intermittently?" If you cannot answer those questions before the system goes to production, you do not actually know how your system behaves.

A useful exercise before any multi-region design review: take your architecture diagram and draw an X through each link and each region, one at a time. For each X, describe out loud what happens. If you ever say "I am not sure" or "I think we fall back to..." you have found a gap that must be resolved before the design is complete.

---

### A Note on Observability in Multi-Region Systems

All of the failure detection and automated responses described in this chapter depend on one thing: you can actually measure what is happening in each region in real time. Observability in multi-region systems has specific requirements that single-region systems do not face.

**Cross-region observability aggregation:** your monitoring dashboards must aggregate metrics from all regions into a single view. If your Grafana only shows US-East metrics, you will be flying blind during a EU-West incident. Use a global metrics store (Datadog, New Relic, or a multi-region Prometheus federation) that ingests metrics from every region.

**The observer effect problem:** if your monitoring infrastructure itself lives in one region (say, US-East), and US-East partially degrades, your ability to monitor US-East's own health is degraded. A partially failing region's metrics may stop flowing to your monitoring system — making the region look healthy on your dashboard just as it starts to fail. Mitigation: synthetic health probes from multiple external vantage points independent of your infrastructure (Pingdom, StatusCake, Route53 health checks, Datadog synthetic monitors). These check your service from outside your infrastructure and will still report even if your internal observability pipeline is broken.

**Centralized vs. distributed alarming:** if alarms are evaluated in a single region's monitoring system, a partition that isolates that region from the others can blind your alerting entirely. Large companies (Google, Meta, Amazon) run their monitoring and alarming systems in multiple regions with independent pipelines. If US-East's monitoring pipeline is down, EU-West's pipeline independently detects the same alerts and pages the on-call engineer.

For a Staff-level interview: "We would use Datadog with agents in all three regions feeding a single global account. We would supplement with Route53 health checks (evaluated by AWS independent of our infrastructure) and Pingdom synthetic monitors from external vantage points, so our ability to detect failures does not depend on the failed region's own infrastructure being functional."

---

### Making RTO and RPO Concrete: The Time Budget

Most engineers use the terms **RTO** (Recovery Time Objective — how long until the system is back to serving users acceptably) and **RPO** (Recovery Point Objective — how much data loss is acceptable) without specifying where each second comes from. At Staff level, you must be able to decompose your RTO into its sequential steps and defend the total.

**Breaking down a realistic RTO for DNS-based active-passive failover (three-region, TTL=60s):**

```
Step                               Duration  Cumulative
---------------------------------- --------- ----------
Failure onset                      T=0       T=0
First Route53 health check fires   +30s      T=30s
  (check interval = 30 seconds)
Second check fails                 +30s      T=60s
Third consecutive check fails      +30s      T=90s
  -> Route53 marks region UNHEALTHY
New DNS queries return failover IP +0s       T=90s
  (immediate after unhealthy mark)
Existing DNS cache expires (worst) +60s      T=150s
  (TTL=60s, user resolved at T=89s,
   cache expires at T=89+60=T=149s)
Fencing script executes            +5s       T=155s
Database promotion completes       +30s      T=185s
Load balancer routing updated      +10s      T=195s
Monitoring confirms SLO met        +15s      T=210s

TOTAL RTO: ~210 seconds (3.5 minutes)
```

This is not a vague "a few minutes." It is a specific, defensible number derived from actual component latencies. Now you can reason about how to improve it:

- Cut check interval from 30s to 10s, threshold stays at 3: detection drops from 90s to 30s. Saves 60s.
- Cut TTL from 60s to 10s: cache expiry drops from 60s to 10s. Saves 50s.
- After both changes: total RTO falls from 210s to approximately 100s.
- To get below 60s total: DNS-based failover cannot achieve it. You need Anycast or pre-connected cross-region proxy paths at the CDN layer to bypass DNS TTL entirely.

**RPO budget for async replication:**

```
RPO = replica lag at the moment the failover decision is made

Normal conditions:
  - Async replica lag: 0.1 to 2 seconds
  - RPO commitment: "< 5 seconds" is achievable

Degraded network (partial partition):
  - Async replica lag may grow to 30-60+ seconds during the degradation
  - RPO at time of forced failover may exceed 30 seconds
  - This must be documented: "During network degradation scenarios,
    RPO may extend to 60 seconds. We alert at 20s lag as early warning."

Sync replication (writes blocked until both regions confirm):
  - RPO: ~0 seconds (no data loss)
  - Cost: every write adds cross-region RTT (~80ms) to write latency
  - Trade-off: RPO=0 vs. write latency +80ms on every transaction
```

Documenting your RPO and RTO numbers — and the failure conditions under which they may be breached — is a first-class Staff engineering deliverable. It forces you to think through the failure path concretely, sets clear expectations with your product stakeholders, and gives your SRE team a measurable target to test against during game days.

---

*End of Chapter 36, Part C.*
# Chapter 36: Multi-Region Systems — Part D
## Applied Examples, Evolution, Monitoring, and Organizational Reality

---

## 1. Applied Example 1: User-Facing API at Global Scale

### The Problem

Imagine you run a cafeteria with three locations — one in New York, one in Paris, one in Tokyo. The menu is the same everywhere. Most customers just read the menu board or check what the daily special is. A few actually place orders. You take orders locally and eventually synchronize the kitchen inventory across all three locations. If Tokyo is briefly out of sync on inventory, a customer there might briefly see yesterday's special listed. That is annoying, not catastrophic.

That is Twitter at global scale.

The actual numbers: 300 million users. 40% sit in the US, 35% in the EU, 25% in Asia. Of all requests hitting your servers, 95% are reads — someone loading their timeline, checking a profile, searching for a hashtag. Only 5% are writes — posting a tweet, hitting follow, liking a post.

Your target: **p99 latency** (the 99th-percentile response time — meaning 99 out of 100 requests finish within this time) must be under 200 milliseconds globally. And you need **99.99% availability** — less than 52 minutes of downtime per year across the entire calendar year.

The question is not just "how do we serve 300 million users fast enough." The question is "which 5% of our requests actually require global consistency, and which 95% can tolerate a few seconds of lag?" Answering that question correctly determines the entire architecture.

---

### Architecture Decision Process — Staff-Level Thinking

A junior engineer sees "global scale" and immediately says "we need active-active multi-region with strong consistency everywhere." A staff engineer slows down and works through four sequential questions before drawing a single box on a diagram.

**Step 1: What does consistency actually need to be for writes?**

Ask this precisely: "If a user posts a tweet in New York at 2:00:00 PM, and a user in Tokyo does not see that tweet until 2:00:03 PM — does anyone get hurt?"

Work through the consequences. No money changes hands. No safety risk exists. Nobody's account is compromised. A 3-second delay on social content is invisible to real human users — humans do not notice 3-second information propagation delays in social feeds. This means **eventual consistency** — where all replicas eventually converge to the same state, but may be briefly out of sync — is acceptable for writes on social content.

You do not need to pay the cost of **synchronous cross-region replication** (where the write does not return success until every region in the world confirms it). Synchronous replication across continents costs 150–300ms per write and adds complexity around partial failures. For social content: completely unnecessary.

**Step 2: Where should reads go?**

Reads are 95% of traffic. This is the dominant cost and the dominant latency contributor. If you force every Paris user to read from a database in Virginia, you add 80–120ms of round-trip latency just for the transatlantic ocean crossing. That 80–120ms alone uses up most of your 200ms p99 budget before your application logic even runs.

Decision: **regional read replicas**. Each region keeps a local copy of the data, continuously updated from the primary via asynchronous replication. Paris users read from Paris. Tokyo users read from Tokyo. 95% of your traffic gets local latency — typically 5–30ms instead of 100–150ms. This is the single highest-leverage architectural decision for a read-heavy global system.

**Step 3: Where should writes go?**

Writes are only 5% of traffic. You have two choices here: (a) **write-local**, where each region has its own write-capable primary database and accepts writes directly, or (b) **write-central**, where all writes in the world go to one designated primary region.

Write-central is dramatically simpler. There is only one source of truth. Replication is one-directional (primary to replicas). There are no write conflicts to resolve, no concurrent writes to the same record from different regions to reconcile. The downside: users writing from non-primary regions pay a cross-region latency tax on every write.

The numbers for this system: a Paris user posting a tweet pays an extra 80–100ms for the transatlantic round-trip to US-East primary. Their total write latency might be 150ms. That is within budget. For a social media post action — something a user does at most a few times per hour — this is completely acceptable. Write-central wins for US and Asia users.

**Step 4: What about EU data residency?**

Here is where legal reality overrides engineering preference, and this is something staff engineers must internalize. GDPR — the General Data Protection Regulation, Europe's sweeping data privacy law — requires that EU citizens' personal data be stored and processed within the European Union. You cannot send a Paris user's account data to Virginia for writes and store the primary copy there.

This is not a performance decision. It is not optional. It is a legal requirement with fines of up to 4% of global annual revenue. For a company with $5 billion annual revenue, a major GDPR violation could cost $200 million.

For EU users: you need a **write-local EU primary**. EU users write to EU-West. Their data lives in EU-West. EU-West is an independent write-capable primary for EU user data. This adds complexity — now you have two primaries — but the alternative is regulatory exposure you cannot accept.

---

### Final Architecture

Three regions: **US-East** (Virginia), **EU-West** (Ireland or Frankfurt), **AP-Tokyo**.

Write routing by user:
- US users: write to US-East primary. No cross-region hop.
- Asia users: write to US-East primary. 140–180ms write latency, acceptable for social content, no regulatory barrier.
- EU users: write to EU-West primary. Local write latency, GDPR compliant.

Read routing:
- All users read from their local region's read replica.
- US-East replica serves US reads.
- EU-West replica serves EU reads (including EU users reading US users' content — served from EU-West replica of that content).
- AP-Tokyo replica serves Asia reads.

Replication topology:
- US-East primary replicates asynchronously to EU-West replica and AP-Tokyo replica.
- EU-West primary replicates asynchronously to US-East replica and AP-Tokyo replica.
- AP-Tokyo is read-only replica only (no primary). Asia users write to US-East.
- SLA: replication lag stays under 5 seconds for user-facing content under normal conditions.

```
+-------------------+    async replication    +-------------------+
|    US-EAST        | ----------------------> |    EU-WEST        |
|                   |                         |                   |
| [Write Primary]   | <---------------------- | [Write Primary]   |
|  (US + Asia       |  bidirectional async    |  (EU users only,  |
|   users)          |                         |   GDPR required)  |
| [Read Replica]    |                         | [Read Replica]    |
| [App Servers]     |                         | [App Servers]     |
+--------+----------+                         +---------+---------+
         |                                              |
         |  async replication                           | async replication
         v                                              v
+-------------------+
|    AP-TOKYO       |
|                   |
| [Read Replica     |  <-- receives from both primaries
|  only]            |
| [App Servers]     |
+-------------------+

WRITE PATHS:
  US user  -----> US-East Primary    (local write, fast)
  Asia user ----> US-East Primary    (cross-Pacific, 140-180ms, acceptable)
  EU user  -----> EU-West Primary    (local write, fast, GDPR compliant)

READ PATHS:
  US user  -----> US-East Replica    (local, 5-30ms)
  EU user  -----> EU-West Replica    (local, 5-30ms)
  Asia user ----> AP-Tokyo Replica   (local, 5-30ms)

REPLICATION FLOW:
  US-East Primary --[async]--> EU-West Replica   (lag: 1-5 seconds)
  US-East Primary --[async]--> AP-Tokyo Replica  (lag: 1-5 seconds)
  EU-West Primary --[async]--> US-East Replica   (lag: 1-5 seconds)
  EU-West Primary --[async]--> AP-Tokyo Replica  (lag: 1-5 seconds)
```

---

### Handling the Two Key Replication Scenarios

**Scenario A: A US user reads their own tweet immediately after posting**

The user clicks "Post." The write lands on US-East primary. The database confirms the write. The app returns "tweet posted" to the user. The user immediately scrolls down to see their timeline — which goes to the US-East read replica. The replica is behind the primary by 50–500ms. Their tweet may not be in the replica yet.

This violates **read-your-own-writes consistency** — a core user expectation that you always see your own most recent writes immediately. Violating this is not just a consistency problem; it is a visible product defect. The user thinks their tweet vanished.

Solution: **sticky reads after write**. When a user writes, record a timestamp and a session cookie. For the next 5 seconds, route that user's reads to the primary directly (bypassing the replica). After 5 seconds, replication has caught up (your SLA is < 5 seconds lag) and reads can safely return to the replica. This is a narrow exception — only 5% of users are even writing at any moment, and only for 5 seconds after each write — so it does not meaningfully overload the primary.

Alternative approach: track the **replication position** (a log sequence number) at the time of write, pass it in subsequent read requests, and route reads to the replica only once the replica confirms it has replayed past that position. This is more precise but requires more plumbing. For most systems, the 5-second sticky-read approach is simpler and good enough.

**Scenario B: An EU user reads a US user's tweet**

The US user posts at 14:00:00 UTC. The tweet lands in US-East primary. Async replication starts. It arrives at EU-West replica at 14:00:02 UTC — 2 seconds later. An EU user in Paris refreshes their timeline at 14:00:01 UTC. The tweet is not there yet. They refresh again at 14:00:03 UTC. Now it is.

Is this acceptable? Yes. Social content has no hard consistency requirement. Users do not know that a tweet exists until they see it, so the 2-second absence is invisible to them. Every major social platform — Twitter, Instagram, TikTok, Facebook — operates on this model. The technical term is **eventual consistency with bounded staleness** (the staleness is bounded at under 5 seconds by your SLA).

The only scenario where this would matter: if the EU user and US user are on a video call watching each other's screens and counting seconds. That is not a normal usage pattern your system needs to optimize for.

---

## 2. Applied Example 2: Authentication System

### Why Auth Is Different — The Strictest Consistency Requirement

Picture this scenario carefully. A user's laptop gets stolen at an airport. The theft happens in New York at 3:15 PM. The user is shaken but quick — by 3:18 PM, they are at a cafe on another laptop, logging in with their password and clicking "sign out all other sessions." This triggers a session revocation in your system.

In your system, the revocation write lands in US-East primary at 3:18:00 PM. Async replication to EU-West starts immediately. But the thief, who has taken the laptop to a lounge, is accessing the stolen account from London via EU-West. EU-West still has the session marked as valid. For the next 3–8 seconds — or longer if replication lag spikes — the attacker has full account access.

Three to eight seconds is enough time to:
- Export the user's private messages
- Change the account's recovery email address
- Initiate a payment if financial data is stored

This is not a 3-second delay in a tweet appearing. This is an active security breach caused by eventual consistency.

**Authentication systems require synchronous replication for security-critical writes.** The performance cost — 200–300ms added latency for the revocation operation — is worth it. A user doing "sign out all devices" will gladly wait an extra 300ms if it means the attacker is locked out immediately. The alternative is unacceptable.

This is a concrete example of the staff-level principle: **consistency requirements must be analyzed per operation, not per service**. Most auth operations can use eventual consistency. A narrow set of security-critical operations require synchronous replication. Design accordingly.

---

### Architecture Decision

Split auth writes into two tiers based on security sensitivity:

**Tier 1 — Non-security writes** (username changes, display name, preferences, profile photo): write to local primary, async replication to replicas in other regions. Eventual consistency is fine. A username change taking 3 seconds to appear in Tokyo is harmless.

**Tier 2 — Security-critical writes** (session revocation, password reset, MFA device removal, account lockout): **synchronous write to ALL regions**. The operation does not return HTTP 200 until every region's database has confirmed the write. This costs 200–300ms of added latency. For operations a user performs at most a few times per year in an emergency: the cost is completely justified.

Session creation: write to the user's local primary (US-East for US users, EU-West for EU users). Async replication. A newly created session not being visible in Tokyo for 2 seconds is acceptable — the user just authenticated from the US, and they will not be immediately switching to a Tokyo-routed client.

Session validation (the hot path — called on every single API request): read from local region only. Must return in under 5ms. Never routes cross-region. This is the request that happens millions of times per second across your entire platform. It must be local and fast.

---

### The JWT + Revocation List Pattern

**JWT (JSON Web Token)** is a self-contained, cryptographically signed token. The server encodes claims — user ID, roles, expiry timestamp — into a base64 string, signs it with a private key, and hands it to the client. Any server holding the public key can verify the signature in microseconds, with no database lookup. Completely stateless.

This is fast and scales beautifully. But statelessness has a fundamental security flaw: if you issue a JWT with a 24-hour expiry, and at hour 1 the user revokes it (laptop stolen, account compromised), that token still cryptographically validates for the remaining 23 hours. Any server that only checks the signature will accept it indefinitely until it naturally expires.

The naive solution — check a database on every request to see if the token is revoked — destroys your 5ms latency target. Database round-trips take 1–10ms each.

The production solution used by Google, Stripe, Auth0, and most serious auth systems: **short-expiry JWTs (15 minutes) combined with a per-region revocation list in Redis**.

How the full pattern works:

**Issuance**: create a JWT with a 15-minute expiry and a unique token ID (a UUID stored in the JWT's `jti` claim). Store the token ID in the user's active session record. The JWT lives in the client browser or app.

**Revocation**: when the user revokes ("sign out all devices"), you synchronously write the token ID to a Redis set called the **revocation list** in every region. This is a single Redis SADD command per region. Redis confirmations come back in 20–80ms per region (depending on distance). Total synchronous revocation: 200–300ms. The HTTP response returns only after all regions confirm. The token ID is now in every region's revocation list.

**Validation**: on every API request, the auth middleware does exactly two things: (1) verify the JWT signature — this is a pure CPU operation, no network, completes in under 1ms; (2) check if the token's `jti` value is in the local Redis revocation list — a single Redis SISMEMBER command, 1ms. If either check fails, return 401 Unauthorized. Total auth check: 2ms. Target met.

**Expiry cleanup**: JWTs expire after 15 minutes. Revocation list entries for expired tokens are automatically removed (Redis TTL set to match the JWT expiry). The revocation list stays small even at high volume — you only need to track tokens that were revoked before their natural expiry.

```
TOKEN ISSUANCE (async replication is fine)
+----------+   POST /login    +---------------+
|  Client  | ---------------> | Auth Service  |
|          |                  | (US-East)     |
|          | <--------------- |               |
| JWT      |  JWT (15min,     +-------+-------+
| stored   |  jti=uuid-123)           |
| in app   |                          | async: session record replicated
+----------+                          | to EU-West and AP-Tokyo (2-5s)
                                      v
                              +-------+-------+
                              | EU-West Redis |
                              | AP-Tokyo Redis|
                              +---------------+

TOKEN REVOCATION (SYNCHRONOUS to ALL regions)
+----------+  POST /revoke  +---------------+
|  Client  | -------------> | Auth Service  |
|          |                | (US-East)     |
|          |                +-------+-------+
|          |                        |
|          |                        | SYNC: write jti=uuid-123
|          |                        | to ALL regional revocation lists
|          |                        |
|          |                        +----> EU-West Redis SADD (confirm)
|          |                        |      [~90ms round trip]
|          |                        +----> AP-Tokyo Redis SADD (confirm)
|          |                        |      [~140ms round trip]
|          |                        |
|          | <--------------------- | (returns only after all confirm)
|          |  200 OK                |
+----------+  [total: ~280ms]   +---------------+

TOKEN VALIDATION (LOCAL ONLY — runs on every API request)
+----------+ GET /api/feed  +-------------------+
|  Client  | + JWT header-> | AP-Tokyo App Srvr |
|          |                +--------+----------+
|          |                         |
|          |                         | 1. verify JWT sig  (<1ms, CPU only)
|          |                         | 2. SISMEMBER revocation list (1ms)
|          |                         |    local Redis, no network hop
|          |                         |
|          | <---------------------- |
|          |  200 OK or 401          |
+----------+  [total: ~2ms auth]  +-------------------+
```

The 15-minute expiry is key. Even if your revocation synchronization somehow fails (extreme edge case — region completely isolated), the attacker's window is at most 15 minutes before the token naturally expires. After that, re-authentication is required, which hits your fully synchronized auth service again.

---

## 3. Applied Example 3: News Feed / Timeline

### The Fan-Out Problem at Global Scale

When a celebrity with 100 million followers posts a tweet, consider what needs to happen in a naive push-based system: you want to pre-populate that tweet into 100 million users' timeline caches, so that when each of those 100 million users next checks their feed, the tweet is already there and loading is instantaneous.

That means 100 million individual cache-write operations per celebrity post.

Across 3 regions: 300 million write operations triggered by a single post.

Even at a healthy throughput of 1 million writes per second: 300 seconds of sustained write load — 5 full minutes. During those 5 minutes, your write queues are backed up, some users have the tweet in their cache while others don't, and if another celebrity posts during this window, you have now queued another 300 million writes on top. Your write backlog is growing faster than it can drain.

This is the **fan-out problem**, and it scales with follower count. Regular users (500 followers) have trivial fan-out. Celebrities (100M followers) have catastrophic fan-out.

**Solution: lazy fan-out, also called pull-on-read.** Do not push tweet content to follower caches when the tweet is created. Instead, compute each user's timeline when they request it. The computation happens once per user per cache refresh cycle — not once per tweet per follower.

---

### Cache Topology for Global Feeds

Think of the cache as a local newspaper that is reprinted every 30 seconds. Your city does not wait for every breaking story to be finalized before printing. The paper goes out with what is available. If news breaks after the print run, it appears in the next edition 30 seconds later. The newspaper analogy breaks down only in one way: your cache is per-user, not per-city.

Each region maintains a **timeline cache** keyed by user ID, storing the pre-assembled ranked feed for that user:

- **Cache hit rate**: approximately 80% for active users. Most users check their feed multiple times per day — five, ten, twenty times. Only the first check in each 30-second window requires computation. All subsequent checks within that window hit the cache.

- **Cache miss path**: retrieve the list of accounts the user follows from the local read replica (fast, local), pull the most recent N posts from each followed account from the local replica (fast, local), apply ranking algorithm (relevance, recency), cache the result, return to user. This entire path takes 20–100ms on cache miss vs. 2–5ms on cache hit.

- **Cache TTL**: 30 seconds. After 30 seconds, the next request triggers a recomputation. New posts appear within 30 seconds maximum — users see their feed update within half a minute of new posts landing in the local replica.

- **Cache invalidation strategy**: when a user posts, invalidate their own cache entry immediately (so they see read-your-own-writes). For followers' caches: let them expire naturally on the 30-second TTL. The slight staleness is invisible in practice.

- **Cross-region cache consistency**: explicitly not a goal. Paris users have a Paris cache. Tokyo users have a Tokyo cache. They may see slightly different timelines for the same 30-second window. That is fine. The caches converge as new data replicates and TTLs expire.

---

### The Write Path — Posting a Tweet

```
US USER POSTS TWEET:
+----------+  POST /tweet   +------------------+
|  US User |  ----------->  | US-East Primary  |
+----------+                | DB write confirmed|
                            +--------+---------+
                                     |
                     async replication (2-5 seconds)
                                     |
                  +------------------+------------------+
                  v                                     v
        +------------------+                 +------------------+
        | EU-West Replica  |                 | AP-Tokyo Replica |
        | tweet arrives    |                 | tweet arrives    |
        +--------+---------+                 +------------------+
                 |
                 | background fan-out worker (deferred, async)
                 v
        [For each follower of the tweeting user in EU-West:]
        [  - check if follower's timeline cache exists ]
        [  - if yes: invalidate or update in background ]
        [  - if no: skip (will be computed on next cache miss)]

HYBRID FAN-OUT RULE:
  User has <= 10M followers --> push-based fan-out, update caches proactively
  User has  > 10M followers --> skip cache fan-out entirely
                                On read: fetch celebrity posts dynamically
                                and merge with pre-computed non-celebrity feed
```

The celebrity exception matters at scale. If you have 50 celebrities with 50M+ followers, and they collectively post 500 tweets per day, that is 50 × 50M × 3 regions = 7.5 billion potential fan-out operations per day just for celebrity content. With hybrid fan-out, that entire category of write load disappears. Celebrity posts are fetched on read and merged in — this computation is fast (fetch 50 celebrity accounts' latest posts, which are hot in a small in-memory store) and scales with the number of unique readers, not the number of followers.

This approach is documented in Twitter's public engineering blog, Instagram's architecture writeups, and Facebook's Feed team papers. It is not a theoretical optimization — it is the approach that made these systems work at scale.

---

## 4. How Multi-Region Systems Evolve Over Time

### Phase 0: Single Region — The Right Start

Here is an unpopular truth: most systems should start with a single region and stay there for their first 1–3 years. Many systems should stay there indefinitely.

Think of it like a restaurant chain. You do not open five branches on day one. You open one restaurant, perfect the menu, nail the operations, understand your customers, and build a team that knows how things run. Only when the first location is genuinely at capacity and profitable do you open a second.

A single AWS region (say, us-east-1) gives you three **Availability Zones (AZs)** — three physically separate data centers in the northern Virginia area, each powered by independent utility feeds, connected by redundant private fiber at 25 Gbps. An AZ failure — a power outage, a cooling failure, a hardware cascade — automatically routes traffic to the other two AZs. Modern load balancers and managed services handle this in seconds with no human intervention.

AZ failures are the most common class of infrastructure incident at major cloud providers. They happen a few times per year across the industry. Full regional failures — the entire us-east-1 going dark simultaneously — are extraordinarily rare. AWS has had approximately two significant us-east-1 outages in the past decade that lasted more than an hour.

Most L5 engineers look at single-region architecture and say "that's not highly available enough, we need multi-region." Most staff engineers respond: "AZ-level HA handles 95% of real production outages. Full multi-region handles the remaining 5% at 2.5–3x the infrastructure cost and 10x the operational complexity. Show me the business case."

That is not complacency. That is correct risk/cost analysis.

---

### Phase 1: CDN + Read Replicas — The High-Value, Low-Cost Win

This phase gives you 80% of the global latency benefit at roughly 10–15% of the cost of full multi-region active-passive.

**Add a CDN first.** Cloudflare, Fastly, and AWS CloudFront maintain edge nodes in 100–300 cities worldwide. Static content — JavaScript bundles, CSS, images, videos, fonts — is cached at the edge nearest each user. A user in Singapore downloading your React application's 2MB JavaScript bundle gets it from a Singapore CDN PoP in 8ms instead of from a Virginia server in 185ms. This single change eliminates the majority of non-US latency complaints, because most bytes transferred in a typical web application are static assets.

CDNs also cache API responses for endpoints that return identical data to many users: public profiles, trending content, popular search results. By adding a `Cache-Control: public, max-age=30` header to your "get trending hashtags" API, you may cache that response at 300 CDN edges worldwide. Thousands of users in Tokyo all get the same cached response from Tokyo. Zero additional database load.

**Then add a read replica in EU-West.** EU users reading profiles, posts, and search results now get 10–30ms database read latency instead of 130–160ms. Your EU p99 target drops from 300ms (broken) to 80ms (healthy) for read-heavy endpoints.

Writes still go to US-East for most users in Phase 1. For 95% of read-heavy products with no EU data residency requirement: Phase 1 is good enough for years.

Cost of Phase 1: a CDN contract (Cloudflare's Business plan starts at $200/month, Fastly scales with traffic) plus one EU-West database instance (say, $500–2000/month for a reasonable RDS instance). Dramatically cheaper than full multi-region infrastructure.

---

### Phase 2: Full Active-Passive

**Triggers to consider this upgrade**:
- Business contract or SLA requiring RTO (Recovery Time Objective) under 5 minutes for a full regional outage
- Regulatory requirement to have all user data (including EU users) stored in the EU (GDPR compliance at the data-residency level)
- Revenue loss analysis showing that a single regional outage costs more per hour than the annual cost of the passive region

**What changes**: deploy full infrastructure in EU-West — all application services, all databases (as replicas of US-East primary), all caches, all message queues. This region is fully operational but receives no user traffic under normal conditions. It is a warm standby.

**Automated failover**: when US-East becomes unreachable (health checks fail), the automation kicks in:
1. DNS records updated to point to EU-West load balancers (with TTL pre-set to 60 seconds, not 24 hours — this is a critical operational detail that is almost always wrong the first time you check)
2. EU-West database replica promoted to primary (typically 30–90 seconds depending on database type)
3. EU-West application servers start accepting traffic
4. Target: < 2 minutes from failure detection to EU-West serving traffic

**What actually breaks first when you run Phase 2 for the first time**: not the failover automation itself. It is the operational gaps around it.

The DNS TTL was set to 86400 seconds (24 hours) by the engineer who originally configured it, because they were optimizing for DNS query cost, not failover speed. During a failover drill, you discover it takes 20 minutes for users to be routed to EU-West instead of 2 minutes.

The runbook says "promote the EU-West replica to primary" but does not explain which IAM role has permission to run the promotion command, and the engineer on call cannot find it at 2 AM.

The monitoring that should page "US-East unreachable" actually pages "US-East latency high" — a different alert — and the on-call engineer spends 8 minutes investigating latency before realizing the region is actually down.

Every one of these gaps is found during a proper disaster recovery drill. Every company that skips quarterly DR drills discovers them during an actual outage. The engineering principle: **test your failover quarterly, treat it as a production exercise, write up what broke**.

---

### Phase 3: Active-Active for Specific Services

**Triggers to consider this upgrade**:
- EU write latency is now your bottleneck. Phase 2 still routes all writes (except EU-regulated data) through US-East. EU users creating content pay 80–100ms extra per write.
- Write volume has grown to the point where a single primary database is at 70%+ write capacity. Time to distribute writes across regions.
- Engineering leadership has committed to EU data residency for all EU user data (not just the regulation-required subset).

**The key Phase 3 insight**: you do not go active-active everywhere at once. That way lies chaos, split-brain, write conflicts, and very late nights. You identify a subset of services that are architecturally safe for active-active — meaning concurrent writes from multiple regions can coexist without conflict — and migrate those first. Everything else stays in active-passive.

Services that are naturally safe for active-active, ordered by risk:

- **Stateless services** (zero state, zero risk): by definition, any service that holds no state — config servers, token validators, static asset servers — can run in every region simultaneously with no coordination required.

- **Append-only write streams** (very low risk): analytics event ingestion, audit logging, clickstream collection. Each write is a new independent record. Two regions writing to the same log simultaneously cannot conflict — they produce two separate records, both of which are correct.

- **Session validation with short-expiry JWTs** (low risk): as described in Example 2, the revocation list requires synchronous replication but the validation path is purely local. This scales horizontally across regions trivially.

- **User profile writes** (medium risk, needs conflict resolution): user changes their username in the US and EU simultaneously. Which wins? You need a **last-write-wins** policy (the most recent timestamp wins) or a **merge strategy** (take the union of non-conflicting fields). Requires careful implementation.

- **Financial balances, inventory counts, shared counters** (high risk, requires specialized approach): two regions simultaneously decrementing a counter by 1 could both read "10", both write "9", and end up with "9" instead of the correct "8". Requires either routing all writes for a given record to a single region (region pinning) or using a distributed consensus protocol.

---

### Phase Evolution Table

| Phase | Trigger to Upgrade | What Changes | Cost Multiplier | Team Size Needed | Biggest New Failure Mode |
|---|---|---|---|---|---|
| 0: Single Region | Day 1 for any new system | Nothing — this is the start | 1x | 1-3 engineers | AZ failure (rare, auto-healed by cloud provider) |
| 1: CDN + Read Replica | Non-US users complain about latency; read-heavy traffic | Add CDN, add 1-2 regional read replicas | 1.2-1.4x | 2-4 engineers | Replica replication lag causing stale reads for EU users |
| 2: Active-Passive | RTO < 5 min required; EU data residency regulation | Full passive region, failover automation, DR runbooks | 1.8-2.2x | 4-7 engineers | Untested runbooks; DNS TTL set too high; partial failover states |
| 3: Active-Active (partial) | EU write latency bottleneck; write capacity at limit | Write primaries in 2+ regions; conflict resolution | 2.3-3x | 7-12 engineers | Write conflicts; split-brain; configuration drift between regions |
| 4: Global Consistency | Payment systems; globally shared inventory; regulatory auditability | Spanner/CockroachDB; atomic clocks or HLC; global transaction coordination | 10-100x | Dedicated platform team of 5+ | TrueTime skew edge cases; extreme operational cost; vendor lock-in |

---

### Phase 4+: Global Consistency with Region Pinning

This is the endgame tier. It is what Google runs for Gmail, Google Docs, and Google Cloud Spanner itself. It is what Stripe runs for payment ledgers. It is what Cloudflare runs for globally consistent DNS propagation.

**Google Spanner** uses atomic clocks and GPS receivers physically installed in every data center to establish a globally accurate notion of time called **TrueTime**. TrueTime does not just give you the current time — it gives you the current time with an uncertainty bound (typically 1–7 milliseconds). By knowing that "this transaction definitely completed before time T+7ms," Spanner can assign globally ordered transaction timestamps and provide external serializable consistency: reads see all writes that committed before them, everywhere in the world, always.

The engineering achievement is staggering. The operational cost is also staggering. Spanner is meaningfully more expensive than any single-region relational database. It requires specialized knowledge to operate. It was justified for Google because Google's own products (and Spanner as a cloud product) produce billions of dollars in revenue.

**CockroachDB** is an open-source, Spanner-inspired globally distributed database. It uses Hybrid Logical Clocks (HLC) to approximate TrueTime without requiring GPS-synchronized atomic clocks. It provides serializable isolation across regions. It is accessible to companies that do not have Google's datacenter hardware budget.

**When to mention this in interviews**: name-drop Spanner or CockroachDB when the interviewer asks about globally consistent writes — specifically for payment processors, global inventory systems (where two warehouses must not simultaneously oversell the last unit), or globally replicated configuration stores (where a config change must be visible everywhere atomically).

Do not propose it for social feeds, user profiles, analytics pipelines, or any system that tolerates eventual consistency. The cost is unjustifiable, and the interviewer will correctly push back.

---

## 5. Multi-Region Monitoring

### Why Standard Monitoring Is Not Enough

Standard monitoring setups — a Datadog dashboard, Prometheus + Grafana, New Relic APM — are designed around a single-region mental model. One global latency graph. One error rate. One deployment to watch. Alerts are written against single numbers.

Multi-region systems generate qualitatively different observability questions, and those questions require purpose-built answers:

**"Is latency high globally, or only for EU users?"** These have completely different root causes and fixes. Global latency spike: likely a code deployment or database issue. EU-only latency spike: likely a network problem between EU-West and US-East primary, or a EU-West replica falling behind. A dashboard that shows only global-average p99 latency cannot distinguish these cases.

**"Is replication lag spiking in Tokyo because the Tokyo-US network is congested, or because US-East primary is overloaded with writes?"** The fix is different in each case. You need network metrics, primary write throughput metrics, and replication lag metrics in the same view to diagnose this.

**"Did the failover that the automation triggered at 3:47 AM complete correctly, or is the system in a partial half-failover state?"** This is not a graph question — it is a state machine question. Your monitoring must track the system's current operational state, not just its performance metrics.

Single-region monitoring leaves these questions unanswerable. You need a dedicated multi-region observability layer.

---

### The Six Golden Signals for Multi-Region

**Signal 1 — Per-region latency (p50 and p99)**

Track response time separately for each region. Never aggregate globally as your primary operational view — aggregation masks regional degradation. If EU-West p99 spikes to 800ms but US-East and AP-Tokyo are fine at 90ms, a global average might show 310ms. That looks yellow. It should be red — 800ms p99 is an outage for EU users.

Instrument this at the load balancer level (before requests reach application servers) so you capture DNS resolution time and connection establishment, not just application processing time.

Alert threshold: per-region p99 exceeding 150% of that region's rolling 7-day baseline for more than 2 consecutive minutes.

**Signal 2 — Replication lag**

The time delta between a write landing on the primary and that same write appearing on a read replica. Measured in seconds. This is arguably the most important metric unique to multi-region systems — it tells you how stale your reads are and how long your read-your-own-writes sticky window must be.

Normal values: 0.1–2 seconds for geographically separated regions under normal load. Values above 5 seconds indicate a problem. Values above 60 seconds indicate a serious problem requiring immediate investigation.

Alert thresholds: > 5 seconds for user-facing replicas (warn, Slack notification). > 30 seconds (page on-call). > 5 minutes (critical alert, potential data divergence if primary fails).

**Signal 3 — Cross-region error rate**

Errors specifically on network calls that traverse region boundaries: writes forwarded from EU-West app servers to US-East primary database, replication heartbeat calls between regions, synchronous revocation calls in the auth system. These calls have a baseline error rate of nearly zero under normal conditions (< 0.01%). Any meaningful spike indicates inter-region network degradation.

Causes when it spikes: AWS inter-region backbone congestion event, a BGP routing change that affects the path between two regions, a regional firewall rule incorrectly applied. These events are rare but happen — every large cloud provider has had inter-region connectivity degradation events at least once per year.

Alert threshold: > 0.1% for 1 minute (warn). > 0.5% for 30 seconds (page on-call — this is actively affecting writes).

**Signal 4 — Failover state**

A single piece of metadata that describes the current operational topology: which regions are active, which are passive, whether any failover is in progress, and when the last failover occurred. This is not a metric with thresholds — it is a state variable.

Make it permanently visible on your main operations dashboard. Engineers should never have to dig through logs to determine whether a failover is in progress. Every on-call engineer woken up at 3 AM should see the current topology state within 10 seconds of opening their laptop.

**Signal 5 — Region health score**

A composite metric that combines per-region latency percentile, error rate, and replication lag into a single 0–100 score. The formula does not matter much — what matters is that it gives you a single number to assess regional health at a glance.

Design it so the score degrades smoothly: 100 is perfect health, 80–99 is normal operating range (minor variance), 50–79 is degraded (something is off, investigate), below 50 is incident (page someone). This prevents alert fatigue from constant minor fluctuations while ensuring serious degradation is immediately visible.

**Signal 6 — Traffic distribution**

What percentage of total platform traffic is each region currently handling? On a normal day, this should closely mirror your user distribution: US-East ~40%, EU-West ~35%, AP-Tokyo ~25%. Deviations from this pattern are early indicators of routing problems.

If US-East suddenly drops from 40% to 5% of traffic: something is wrong with routing to US-East. Maybe the DNS health check threshold is misconfigured and it is incorrectly removing US-East from the rotation. Maybe there is a network problem between certain user ISPs and US-East. Traffic distribution anomalies are often detected here before latency and error metrics react — because requests are being silently dropped or rerouted rather than timing out.

---

### Cross-Region Synthetic Monitoring

You cannot rely only on real user traffic to detect problems. Real traffic tells you when users are already experiencing issues — the incident has been ongoing for minutes by the time your real-traffic metrics react.

**Synthetic monitoring** runs automated, scripted test requests from each region to every other region on a fixed interval (every 30 seconds). These are deterministic probes: the same request, the same data, the same expected response, every 30 seconds, from 3 origins to 3 destinations.

A full 3-region synthetic grid runs 6 cross-region probes every 30 seconds (US->EU, US->Tokyo, EU->US, EU->Tokyo, Tokyo->US, Tokyo->EU) plus 3 intra-region probes.

What synthetic monitoring detects that real-traffic monitoring misses:
- Network path degradation between regions before real traffic is affected (because real traffic is being served from local caches but writes are quietly slowing down)
- A replica that is not receiving replication updates (because real reads still return data — just stale data — with no error signal)
- A failover target that would work in theory but has a misconfigured security group blocking inbound traffic from the other region

Cloudflare operates synthetic monitoring between all 300+ of its Points of Presence worldwide, running continuous probes to detect any inter-PoP degradation before it affects customer traffic. Google's global SRE monitoring infrastructure runs tens of thousands of synthetic probes per minute. For most systems: probing 9 region pairs every 30 seconds is sufficient.

---

### Alerting Hierarchy

```
LEVEL 1 — WARN  (no page, posted to #ops-alerts in Slack)
---------------------------------------------------------------
Conditions:
  - Replication lag > 2 seconds on any replica
  - Per-region p99 > 150% of 7-day baseline for > 2 minutes
  - Cross-region error rate > 0.1% for > 1 minute
  - Region health score drops below 80

Action: Engineer reviews at start of shift or next business hours.
        No immediate action required if condition self-resolves.


LEVEL 2 — ALERT  (pages on-call engineer)
---------------------------------------------------------------
Conditions:
  - Replication lag > 30 seconds on any user-facing replica
  - Any region error rate > 1% for > 1 minute
  - Automated failover triggered (any region)
  - Traffic distribution off by > 20% from expected baseline
  - Region health score drops below 50
  - Cross-region error rate > 0.5%

Action: On-call engineer investigates immediately.
        May declare incident. Escalate if not resolved in 15 min.


LEVEL 3 — CRITICAL  (pages on-call + backup + engineering leadership)
---------------------------------------------------------------
Conditions:
  - Any region completely unreachable from synthetic probes for > 60 seconds
  - Global error rate > 5%
  - Split-brain detected (two primaries both accepting writes)
  - Replication lag > 5 minutes (risk of data divergence on failover)
  - Failover in progress AND target region health score < 50

Action: All-hands incident response.
        Customer communication initiated if > 2 minutes with no resolution.
        Post-mortem required within 72 hours.
```

---

### ASCII Monitoring Dashboard

```
+-----------------------------------------------------------------------+
|  GLOBAL STATUS: NORMAL              Last updated: 2026-06-15 14:32:07 |
|                                                                        |
|  Global p99: 108ms  |  Global error rate: 0.03%  |  Failover: NONE   |
+-----------------------------------------------------------------------+
|                                                                        |
|  REGION HEALTH OVERVIEW                                                |
|                                                                        |
|  +----------------------+  +----------------------+  +---------------+ |
|  | US-EAST    [94/100]  |  | EU-WEST    [88/100]  |  | AP-TOKYO      | |
|  | Status: PRIMARY      |  | Status: REPLICA      |  | [91/100]      | |
|  |                      |  |                      |  | Status:       | |
|  | Traffic:    41%      |  | Traffic:    34%      |  | REPLICA       | |
|  | p50 lat:    18ms     |  | p50 lat:    22ms     |  |               | |
|  | p99 lat:    87ms     |  | p99 lat:   134ms     |  | Traffic:  25% | |
|  | Error rate: 0.02%    |  | Error rate: 0.08%    |  | p50 lat:  25ms| |
|  | Repl lag:   n/a      |  | Repl lag:   1.2s     |  | p99 lat: 112ms| |
|  | (is primary)         |  | [OK - under 5s SLA]  |  | Error:  0.03% | |
|  +----------------------+  +----------------------+  | Repl lag: 2.1s| |
|                                                      | [OK]          | |
|                                                      +---------------+ |
|                                                                        |
|  CROSS-REGION SYNTHETIC PROBES  (last 30s)                            |
|  US-East -> EU-West:    89ms [OK]  EU-West -> US-East:    91ms [OK]   |
|  US-East -> AP-Tokyo:  143ms [OK]  AP-Tokyo -> US-East:  148ms [OK]   |
|  EU-West -> AP-Tokyo:  212ms [OK]  AP-Tokyo -> EU-West:  209ms [OK]   |
|                                                                        |
|  REPLICATION LAG TREND (past 60 minutes)                              |
|  EU-West lag:   |.........___...|  avg: 1.1s  max: 3.2s  [OK]        |
|  AP-Tokyo lag:  |.........._....|  avg: 2.0s  max: 4.7s  [OK]        |
|                                                                        |
|  Last failover: none in past 30 days                                  |
|  DR drill last run: 2026-05-22  Next scheduled: 2026-08-22            |
+-----------------------------------------------------------------------+
```

---

## 6. The Organizational Reality of Multi-Region

### Who Owns What

Multi-region is not just a technical challenge. It is an organizational challenge. In practice, organizational failure modes are often more costly than technical ones.

The most dangerous anti-pattern in multi-region systems: a team deploys their service to three regions because "the deployment pipeline has multi-region configured" — without any discussion of what consistency model their service needs, what their acceptable replication lag is, what their RTO/RPO targets are, or what their service does if EU-West goes offline for 20 minutes.

They have accidentally made themselves multi-region without any of the knowledge required to operate it safely. When an incident happens, they discover these gaps at 2 AM under pressure.

**Staff-level responsibility in a multi-region org**: define ownership. Every service must have a team that can answer five questions without looking things up:

1. **Consistency model**: what are our consistency guarantees to callers? Eventual? Read-your-own-writes? Linearizable? Which operations get which guarantee?
2. **RTO**: if our region goes dark right now, how long before this service is restored? What triggers the failover? Who executes it?
3. **RPO**: if our region goes dark right now, how much data can we lose? Is there data in flight (in Kafka, in write buffers, in the database WAL) that would be lost?
4. **Runbook**: where is the failover runbook? When was it last tested? Who ran the last DR drill and what broke?
5. **Replication lag behavior**: what does this service do if replication lag spikes to 5 minutes? Does it serve stale reads? Does it reject reads? Does it fail open or fail closed?

If a team cannot answer these questions, they should not be running in production multi-region. This is a hard line, and enforcing it is a staff engineer's job.

---

### On-Call in a Multi-Region World

An incident in Tokyo at 3:00 AM local time is 7:00 PM the previous evening in London and 2:00 PM in New York. Who responds?

**Option A: Whoever is closest geographically**: the Tokyo team handles Tokyo incidents, the EU team handles EU incidents, the US team handles US incidents. Simple. But breaks down when incidents span regions (a US-East primary failure affects Tokyo reads), and requires each region to have a fully staffed on-call rotation, which is expensive.

**Option B: Global on-call rotation** (whoever is scheduled is paged regardless of time zone): simple to manage, exhausting for engineers. One person in every team will always be covering nights. Leads to burnout, poor incident response from sleep-deprived engineers, and attrition.

**Option C: Follow-the-sun** — incidents are handled by whichever regional team is currently in business hours, handed off as time zones shift. Tokyo wakes up at 9 AM and picks up incidents that occurred overnight. London takes handoff at 9 AM GMT. New York takes handoff at 9 AM ET. Each team is only on-call during their business hours.

Follow-the-sun is the most humane model at global scale. It requires three things that take real engineering investment:

**Shared incident tracking**: every active incident has a written record that any engineer anywhere can read and understand — current symptoms, timeline, what was tried, what is open. If this lives only in someone's Slack DMs or memory, follow-the-sun fails.

**Structured handoff documentation**: a written handoff note at each shift boundary. Minimum content: current status (resolved/active/monitoring), what happened, what was done, what is still open, who to contact with questions. This takes 10 minutes to write and saves hours of ramp-up time.

**Distributed system knowledge**: the engineer in London covering a Tokyo incident must understand how the Tokyo database failover works. This means documentation, not tribal knowledge. If "how to promote the AP-Tokyo replica to primary" is known only to two engineers on the Tokyo team, that is a single point of knowledge — a reliability risk as serious as a single point of failure in infrastructure.

---

### Configuration Drift: The Silent Killer

Imagine you deploy identical application code and configuration to three regions on January 1st. Everything is the same. All three regions are running the same Docker images, same database parameters, same feature flags.

By April 1st, your three "identical" regions have quietly diverged:

- A new recommendation algorithm is enabled via feature flag in US-East for A/B testing. It was supposed to be enabled globally in two weeks. Three months later, EU-West and AP-Tokyo still have the old algorithm. Nobody noticed because the feature flag rollout was tracked in a spreadsheet that got stale.
- An EU-West database engineer noticed high p99 query times in February and tuned the PostgreSQL `work_mem` parameter from 64MB to 256MB. This was done via the RDS parameter group console and was not tracked in Terraform. The other two regions still have 64MB.
- A security patch for a Redis vulnerability was applied in US-East and EU-West as part of a quarterly security sweep. AP-Tokyo was skipped because the engineer running the sweep noticed the Tokyo maintenance window conflicted with a product launch and decided to "come back to it." It is now April and the patch has not been applied.

**Configuration drift** is the gradual, silent divergence of infrastructure state across regions. It causes:

- Bugs that reproduce only in EU-West because EU-West has a different database memory setting
- Security vulnerabilities in one region that are patched in others
- Feature behavior that differs by geography — not intentionally, but because of flag inconsistencies
- Mysterious performance differences that take days to root-cause because nobody remembers the tuning change from February

Prevention requires two non-negotiable practices:

**Infrastructure as Code (IaC)**: every piece of configuration — server parameters, environment variables, database settings, feature flag defaults, security group rules, DNS records — is expressed as code using Terraform, Pulumi, or AWS CDK. There is no "clicking in the console to change a setting." The console is read-only for operational investigation. All writes go through code. Code goes through version control. Version control goes through pull request review.

**GitOps with atomic multi-region deployment**: every configuration change merges to main, which triggers a deployment pipeline that deploys the change to all regions in sequence (US-East first, then EU-West after smoke tests pass, then AP-Tokyo after EU-West smoke tests pass). The deployment does not complete until all regions are confirmed updated. If EU-West deployment fails, AP-Tokyo deployment does not start. The pipeline halts and alerts.

These two practices together make configuration drift structurally impossible under normal operations. Drift can still happen during incidents (when engineers make emergency manual changes and promise to "codify later") — which is why post-incident reviews must always include a step: "were any manual changes made during this incident that need to be codified in IaC?"

---

### The Cost Conversation with Stakeholders

Engineering leadership and finance will eventually ask: "We are spending $3.6 million per year on multi-region infrastructure. Justify this."

A staff engineer needs a rigorous quantitative answer, not a qualitative "it is important for reliability."

The framework for expected value of multi-region infrastructure:

```
Annual expected value =
    P(regional failure per year)
  x (downtime duration without multi-region - downtime with multi-region)
  x downtime cost per hour
```

Work through a concrete example:

- Company revenue: $500M per year
- Revenue per hour: $500M / 8760 hours = $57K per hour
- Estimated additional costs during outage (SLA penalties, support surge, recovery work): +40% premium
- Effective downtime cost: $80K per hour

- Historical rate of regional-level outages in the industry: approximately 1 significant incident per year per major cloud region
- RTO without multi-region (single-region active-passive with manual failover): 45–90 minutes
- RTO with multi-region (automated failover): 1–3 minutes
- Time saved per event: ~60 minutes = 1 hour

- Expected value per year: 1 event/year × 1 hour saved × $80K/hour = **$80K/year**

If your multi-region infrastructure costs $3.6M/year, the pure-availability ROI does not justify it. You need additional justification:

- **GDPR compliance**: potential fine for non-compliance is 4% of global revenue = $20M. Annual compliance infrastructure: $1M. Clearly justified.
- **Latency-driven revenue**: A/B tests at Amazon found that 100ms of added latency reduced revenue by 1%. For a $500M/year e-commerce business: 100ms improvement in EU latency (from single-region to multi-region) could recover $5M/year in EU revenue.
- **Competitive positioning**: enterprise customers in the EU require data residency commitments as a condition of signing. Without EU-region deployment, you cannot close certain deals.

The point: the cost justification must be explicit and numerical. "Multi-region is worth it" is not a staff-level answer. "Multi-region is worth it because GDPR compliance alone prevents a potential $20M fine and enables $8M in EU enterprise deals that require data residency commitments" is.

---

### Regional Compliance and Data Sovereignty

This is the domain where engineering preferences carry the least weight. Legal requirements are not negotiable. Regulatory fines are not theoretical. Staff engineers in global companies must have a working knowledge of which data regulations apply to their system.

**GDPR (EU General Data Protection Regulation)**: applies to any company that processes personal data of EU citizens, regardless of where the company is headquartered. "Personal data" includes names, email addresses, IP addresses, location data, behavioral tracking data, and any other information that can identify a natural person.

Architectural implication: if you store EU user personal data on a US server, you are potentially in violation. Transfers to non-EU countries require one of several legal mechanisms (Standard Contractual Clauses being the most common). The safest architectural approach: store EU user personal data in EU-located infrastructure and do not transfer it outside without explicit legal mechanism in place.

**PIPL (China's Personal Information Protection Law)**: applies to processing of Chinese citizens' personal data. Requirements include: data must be stored in China, cross-border transfer requires a government security assessment for large-scale data exports, the controller must appoint a domestic representative.

Architectural implication: if you serve Chinese users, you need a separate China deployment, isolated from the rest of your global infrastructure. AWS China, Azure China, and Alibaba Cloud all provide China-region options — but they are operated by Chinese local entities under Chinese regulatory jurisdiction, not directly by the US parent company. Your China deployment is architecturally separate: different IAM policies, different data pipelines, different incident response contacts.

**What this means for your global data architecture at staff level**:

You cannot build a single global data lake that streams all user events regardless of origin. EU user events must stay in EU infrastructure. China user events must stay in China. Your analytics platform must respect these boundaries.

The practical question to ask for every data flow you design: "Does this data contain regulated personal information? If yes: which users does it cover? Which jurisdictions' laws apply? Does this flow cross those boundaries?"

The category distinction that matters most in practice:

- **Individual user records** (profile data, behavioral events tied to a user ID, location history): almost always regulated personal data in GDPR jurisdictions. Must stay in the correct geographic region.
- **Aggregated anonymized metrics** (what percentage of users clicked on a button, average session duration by country): generally not personal data. Can flow globally. GDPR considers anonymized data outside the regulation's scope if re-identification is not reasonably possible.
- **Pseudonymized data** (events with user IDs replaced by opaque tokens): still regulated under GDPR (the token can be re-linked to the user via the mapping table). Do not treat pseudonymization as the same as anonymization.

Staff engineers are expected to know these distinctions and proactively apply them when designing new data flows, not wait to be told by the legal team.

---

## 7. Multi-Region Failure Modes and How to Handle Them

### The Failure Mode Catalog

Every architecture has a set of characteristic failure modes — things that go wrong in ways specific to that architecture's structure. Single-region systems fail in simple ways: a server dies, a database runs out of disk, a deploy goes bad. Multi-region systems fail in more complex ways, often involving interactions between regions that are difficult to reproduce in a test environment.

Staff engineers are expected to know the failure mode catalog for multi-region systems, have opinions on which modes are most dangerous, and have specific mitigation strategies ready.

---

### Failure Mode 1: Replication Lag Spike

**What happens**: under normal conditions, your US-East primary replicates to EU-West replica in 1–3 seconds. Under load — a major product launch, a viral event, a DDoS attack — write volume to US-East spikes 10x. The replication channel can only push so many bytes per second. EU-West replica falls behind: 5 seconds, 30 seconds, 2 minutes, 10 minutes.

EU users are now reading data that is 10 minutes stale. For social content, this is annoying but not catastrophic. For user account data — "my account settings aren't saving" — it looks like a bug. For financial data, it is a serious problem.

**Detection**: replication lag metric spikes past alert threshold. This is what Signal 2 in your monitoring suite catches.

**Mitigation options**:
- **Read routing fallback**: when EU-West replica lag exceeds threshold (say, 30 seconds), route EU reads temporarily to US-East primary (accepting the latency hit) rather than serving stale data. This is a traffic routing rule in your load balancer or service mesh.
- **Write throttling**: when primary write volume is causing replica lag, apply backpressure on writes — queue write requests, slow down acceptance rate, return HTTP 429 to low-priority write traffic (analytics events, passive tracking) while prioritizing user-facing writes.
- **Replication channel capacity**: provision dedicated network bandwidth for the replication path. AWS offers enhanced inter-region connectivity (up to 100 Gbps between supported regions). Do not let replication compete with regular API traffic on a shared network link.

---

### Failure Mode 2: Network Partition Between Regions

**What happens**: the network path between US-East and EU-West goes down. Not the entire AWS US-East region — just the connection between the two regions. This is called a **network partition** or sometimes a **split** event. Both regions are fully operational internally. They just cannot talk to each other.

Now your system must make a choice. This is the **CAP theorem** in practice:
- If you want **consistency** (reads always return current data): you must reject writes in EU-West (since they cannot replicate to the primary) and reject reads from EU-West replica (since you do not know how stale it is). EU-West goes down for user-facing traffic. You have sacrificed availability for consistency.
- If you want **availability** (EU-West stays up and serves traffic): you accept that EU-West is serving potentially stale data and accepting writes that may conflict with US-East. You will have to resolve conflicts when the partition heals. You have sacrificed consistency for availability.

For most social/content systems: prefer availability. EU-West keeps serving reads from its replica (accepts some staleness) and continues to accept writes into a local buffer (reconciles when partition heals). Users experience minor staleness, not an outage.

For authentication/financial systems: prefer consistency. When the partition heals, fail open cautiously — validate with primary before accepting auth from EU-West replica.

```
NORMAL STATE:
  US-East Primary <---[replication 1-3s]---> EU-West Replica
  US-East Primary <---[writes forwarded]---> EU-West App Servers

PARTITION (US-East <-> EU-West link fails):
  US-East: operating normally, accepting all writes
  EU-West: isolated
    - Replica is now 0 seconds stale (at the moment of partition)
    - Every second that passes: replica falls 1 second further behind
    - App servers can still READ from local replica (serves increasingly stale data)
    - Writes: two options
      (a) reject all writes (EU-West goes read-only)
      (b) buffer writes locally, reconcile after partition heals

PARTITION HEALS (network restored after T minutes):
  - EU-West replica must catch up T minutes of replication lag
  - Buffered writes must be replayed to US-East primary
  - Conflict resolution needed if same records were written in both regions
```

**Detection**: cross-region synthetic probes fail between US-East and EU-West. Cross-region error rate spikes to 100%. This triggers Level 3 Critical alert immediately.

**Mitigation**: partition detection must be fast (30-second synthetic probes achieve 30-second detection time). Automated partition response policy (configured in advance): route EU-West to read-only mode, or continue serving with staleness acceptance, based on the service's configured policy. Human escalation for partition lasting longer than 5 minutes.

---

### Failure Mode 3: Split-Brain

**Split-brain** is the most dangerous failure mode in multi-region systems. It occurs when two regions both believe they are the authoritative primary and both accept writes to the same data simultaneously.

How it happens: US-East primary appears to go down (network issue prevents EU-West from reaching it). EU-West's automated failover triggers: it promotes its database to primary and starts accepting writes. US-East was not actually down — just unreachable from EU-West. Now two regions are both accepting writes as primary. Split-brain.

Two databases, both accepting writes to the same user records, with no way to know which write should "win." Every second of split-brain increases the data that will need conflict resolution. Some conflicts (like a counter being incremented on both sides) may be mathematically unresolvable without data loss.

```
SPLIT-BRAIN SCENARIO:

Time 0:  US-East Primary   ---[link fails]---  EU-West Replica
                            (EU-West cannot reach US-East)

Time 30s: EU-West automatic failover triggers
          EU-West promotes itself to Primary
          EU-West begins accepting writes

Time 30s: US-East still operating as Primary (was never down)
          US-East continues accepting writes

Now: TWO PRIMARIES
  US-East Primary (accepting writes from US users)
  EU-West Primary (accepting writes from EU users)
  Same user data being written in both regions with no reconciliation

Time 5min: network link restored
  PROBLEM: both regions have 5 minutes of divergent writes
  Which username change wins? User changed name in US at T+1min
  and in EU at T+2min. One of these is wrong. One user's change
  is discarded. Data loss.
```

**Prevention**:
- **Quorum-based failover**: EU-West only promotes itself if it loses contact with US-East AND a majority of "witness" nodes (third-party observers) also cannot reach US-East. This requires US-East to be truly unreachable, not just network-partitioned from EU-West specifically.
- **Fencing tokens**: when EU-West promotes itself, US-East's database is sent a "fence" command that prevents it from accepting writes until explicitly unfenced by a human operator. This sacrifices some availability (US-East goes read-only) to prevent split-brain.
- **Human-in-the-loop for primary promotion**: for the highest-risk systems, automated failover stops short of promoting a new primary. It routes traffic away from the suspect primary and pages a human to make the final call. Adds 5–10 minutes to RTO, prevents split-brain entirely.

---

### Failure Mode 4: Cascading Cross-Region Load

**What happens**: EU-West read replica falls behind (replication lag spike). You have a mitigation: when lag exceeds threshold, route EU reads to US-East primary. You enable this routing fallback.

Now EU's read traffic — 34% of your total platform traffic — is hitting US-East primary alongside US traffic. US-East primary is now handling 75% of global read traffic (40% US + 34% EU) plus 100% of global writes. Write latency on US-East spikes because it is competing with reads for I/O. AP-Tokyo replica also falls behind (same replication channel is now congested with more read traffic on the primary). You route AP-Tokyo reads to US-East primary too. Now US-East is handling 100% of reads globally. US-East saturates and latency spikes globally.

Your mitigation for EU replica lag caused a global outage by cascading load onto the primary.

This is a **cascading failure** — one mitigation creates a worse problem downstream.

**Prevention**:
- Never route reads from a stale replica to the primary without also enforcing a strict traffic cap (max X% of read traffic ever hits the primary)
- Separate read replicas for replica-fallback traffic from primary replicas (so failover reads go to a dedicated "overflow" replica, not the true primary)
- Load shed at the primary: the primary has a hard connection limit; when reached, it rejects new connections with an explicit "overloaded" error rather than degrading silently for all traffic

---

### Chaos Engineering for Multi-Region Systems

**Chaos engineering** is the practice of intentionally introducing controlled failures into your system in production (or a production-equivalent environment) to test its resilience before real failures occur.

Netflix famously invented this approach with their **Chaos Monkey** tool, which randomly terminates virtual machines in production. They later extended it to **Chaos Kong**, which terminates an entire AWS region in production to test cross-region failover. This is extreme and only appropriate for companies with extremely mature resilience practices.

For most engineering teams, a more measured approach works:

**Level 1 — DR drills** (low risk, high value): quarterly exercise where a senior engineer simulates a regional failure by manually taking the primary offline in a staging environment and timing the failover. Validates runbooks without touching production.

**Level 2 — Replica lag injection** (medium risk): deliberately throttle the replication channel in a staging environment to 10% of normal speed. Watch how the system behaves when replica lag is at 5 minutes. Does monitoring alert correctly? Do the fallback read routes trigger? Does the load on the primary stay within bounds? Fix what breaks before it happens in production.

**Level 3 — Production partition simulation** (higher risk, done rarely): use a network ACL or firewall rule to block inter-region traffic between US-East and EU-West for 30 seconds in a low-traffic window. Verify that split-brain prevention works as designed. Verify that partition detection fires within 30 seconds. Verify that EU-West degrades gracefully. Restore the link. Verify that reconciliation works.

The goal is not to cause outages — it is to find the gaps in your resilience design before a real failure does. Companies that never test their failover mechanisms always discover the gaps during real incidents, at 2 AM, under pressure.

---

## 8. Interview Strategy for Multi-Region Questions

### Recognizing the Multi-Region Question

Multi-region does not always come up explicitly. These interview prompts all require multi-region thinking:

- "Design Twitter / Instagram / YouTube for 300 million users globally."
- "Design an authentication service that needs to be available in EU and US."
- "Our payments system needs to be compliant with GDPR."
- "We need 99.99% availability for this service."
- "How would you reduce latency for our international users?"

The signal to start discussing multi-region: any combination of "global," "international users," "latency," "availability SLA," or specific regulatory requirements (GDPR, PIPL).

---

### The Four-Step Framework for Any Multi-Region Question

**Step 1: Establish consistency requirements before any architecture.**

Say explicitly: "Before I draw any architecture, I want to understand the consistency requirements for each operation." Then ask or assert: which operations are read? Which are write? For writes: is eventual consistency acceptable, or is there a case where eventual consistency causes business or security harm?

This signals to the interviewer that you know the fundamental tradeoff. Most candidates skip directly to "we need multi-region" without ever questioning what consistency they need.

**Step 2: Identify the regulatory constraints.**

Ask or assert: "Are there data residency requirements? GDPR for EU users? PIPL for China users?" This signals awareness of the real-world constraints that often drive multi-region decisions more than performance does.

**Step 3: Size the traffic asymmetry.**

What percentage of traffic is reads vs. writes? If 95% reads: your primary architectural lever is regional read replicas. If 50% reads / 50% writes: you have a harder problem. Work through where each type of traffic should go.

**Step 4: Choose the right phase for the system's maturity.**

Do not propose Phase 3 active-active for a system that is described as "early stage" or "needs to be built in 6 months." Propose the right phase for the stated context. If the system is described as serving a global enterprise customer base with SLA requirements: jump to Phase 2 active-passive minimum.

---

### Common Interview Mistakes and How to Avoid Them

**Mistake 1: Proposing strong global consistency for everything.**

If you say "all data is synchronously replicated to all regions on every write," the interviewer will correctly push back: this makes every write take 200–300ms globally and creates a complex failure scenario if any region is unreachable. Reserve synchronous replication for security-critical operations only.

How to avoid: explicitly state the consistency model per operation type. "For user profile writes, eventual consistency is fine — 3 seconds of lag is harmless. For session revocations, I want synchronous replication — the security cost of eventual consistency is unacceptable."

**Mistake 2: Forgetting failover behavior.**

Many candidates describe a beautiful multi-region steady-state architecture and never address "what happens when a region goes down." The interviewer will ask. Have an answer ready: which region fails over to which? What triggers failover? How long does it take? What is the data loss exposure (RPO)?

**Mistake 3: Treating multi-region as always better.**

Some interviewers deliberately bait candidates with "would you make this multi-region?" for a system that clearly does not need it (an internal admin tool, a batch processing pipeline with no user-facing latency requirement). The right answer is "No, this system does not need multi-region, and here is why" — not "Yes, we should always be multi-region."

**Mistake 4: No mention of cost.**

Multi-region doubles or triples infrastructure cost. A strong candidate mentions this and offers a brief justification or acknowledges the tradeoff. "This active-passive design roughly doubles our infrastructure cost. That's justified by the RTO requirement and the cost of an outage for this business."

---

### The Quick Multi-Region Decision Tree for Interviews

```
Does the system serve users in multiple continents?
  |
  +-- No --> Single region with CDN. Done.
  |
  +-- Yes
       |
       Are there EU users with personal data?
         |
         +-- Yes --> Must have EU-based primary for EU user writes (GDPR)
         |
         +-- No --> Can use write-central to US-East primary
         |
       What is the read/write ratio?
         |
         +-- > 80% reads --> Regional read replicas. High impact, low cost.
         |
         +-- Mixed (>30% writes) --> Consider write-local for latency-sensitive writes
         |
       What is the consistency requirement for writes?
         |
         +-- Social content, profiles --> Eventual consistency OK
         |
         +-- Security (revocations, passwords) --> Synchronous replication required
         |
         +-- Financial (balances, payments) --> Strong consistency required (Spanner tier)
         |
       What is the RTO requirement?
         |
         +-- < 15 minutes, no contract SLA --> Single region + AZs is fine
         |
         +-- < 5 minutes, SLA in contract --> Active-passive minimum
         |
         +-- < 2 minutes, financial/safety --> Active-active for critical services
```

---

### What Separates Good from Great Answers

A **good answer** correctly identifies that reads should go to regional replicas, writes should go to a primary, and names the consistency model (eventual vs. strong).

A **great answer** does all of the above plus:
- Explicitly names the operations that require different consistency than the default (session revocation, balance updates) and explains why
- Addresses the failure case: what happens when a region goes down, how long is the RTO, what is the RPO
- Names the replication mechanism (async with bounded lag SLA) and gives a concrete lag number (< 5 seconds)
- Mentions the organizational concerns without being asked: who owns the runbook, how is failover tested
- Frames the cost tradeoff and justifies the architecture choice at the stated scale

The difference between good and great is not more clever technology. It is treating the problem as a business decision with engineering constraints, not an engineering puzzle with business as a footnote.

---

## 9. Geo-Routing and Traffic Steering Mechanics

### How Requests Actually Find the Right Region

All the regional architecture in the world is worthless if requests from Paris do not actually land in EU-West. The mechanism that routes users to the correct region is **geo-routing** — routing decisions made based on the geographic origin of a request. Understanding how this works at each layer separates staff engineers from engineers who treat it as magic.

There are three layers where geo-routing can operate, and real systems use all three in combination.

---

### Layer 1: DNS-Based Geo-Routing

When a user's browser resolves `api.yourapp.com`, the DNS response determines which IP address — and therefore which region — the request goes to. **DNS-based geo-routing** returns different IP addresses to DNS queries from different geographic locations.

AWS Route 53, Cloudflare DNS, and Google Cloud DNS all support this natively. You configure: "queries from the EU region return the EU-West load balancer IP; queries from Asia return the AP-Tokyo load balancer IP; all others return the US-East load balancer IP."

The DNS resolver knows the approximate location of the requester via the client's IP address. This is accurate at the country level (Paris DNS queries resolve to EU-West IP) but not necessarily at the city level.

**Latency**: the DNS resolution step adds 1–5ms in most cases (resolved from a nearby DNS resolver cache). The first resolution after cache expiry hits the authoritative DNS server — typically another 10–30ms, then cached for the TTL duration.

**TTL tradeoffs**: set DNS TTL too high (24 hours) and failover propagation is slow — users keep hitting the failed region for up to 24 hours after you update DNS. Set TTL too low (30 seconds) and you hit the DNS authoritative server more often, adding query cost and 10–30ms of extra latency on every cache miss. Production recommendation: 60 seconds for user-facing APIs with failover requirements. Longer (300–3600 seconds) for stable services that never need fast failover.

**Limitation**: DNS geo-routing operates at connection establishment time. Once a connection is made, subsequent requests on that same TCP connection go to the same IP. For short-lived HTTP/1.1 connections, this updates frequently. For persistent HTTP/2 connections, a single connection may serve thousands of requests before DNS is re-resolved.

---

### Layer 2: Anycast Routing

**Anycast** is a networking technique where multiple servers worldwide share the same IP address. When a packet is sent to that IP, the internet's routing infrastructure automatically sends it to the geographically nearest server announcing that IP address. No DNS lookup required — the routing decision happens in the network layer itself.

This is how Cloudflare operates its network. A single Cloudflare IP (say, `1.1.1.1` or their origin-facing IPs) is announced from 300+ points of presence worldwide. A request from Paris to a Cloudflare-protected IP is automatically routed to the Frankfurt or Amsterdam PoP, not Virginia, by the internet's own routing protocols (BGP). The user never configures anything. The latency reduction is automatic.

Benefits: faster routing decisions than DNS (network layer vs. application layer), automatic failover as the network reroutes if a PoP goes down, no TTL issues.

Limitations: anycast is IP-level routing, not application-level. You cannot use anycast to route EU database writes to EU-West and US database writes to US-East — that logic must happen in application code. Anycast is primarily used for edge layer routing (CDN, DDoS mitigation, load balancer fronts), not backend service routing.

---

### Layer 3: Application-Level Routing

At the application layer, your own code makes routing decisions. When an EU user's request arrives at the EU-West load balancer, the application service inspects the request and decides where to route the underlying database call.

For read routing: the EU-West application server connects to the EU-West read replica. Straightforward.

For write routing: the EU-West application server must route the write to the correct primary. An EU user's write goes to EU-West primary. But an Asia user who somehow ended up hitting EU-West (maybe via a VPN, maybe via DNS misbehaving) should have their write forwarded to US-East primary.

How does the application server know which primary to use? **User region metadata** stored in the user's account record and/or JWT. When the user authenticates, their region is recorded (EU, US, AP). Subsequent requests carry this in the JWT claims or in a session cookie. The application server reads `user.region` and routes the database write to the appropriate primary.

```
APPLICATION-LEVEL WRITE ROUTING:

Request arrives at EU-West app server
  |
  v
Parse JWT --> extract user.region = "US"
  |
  +-- user.region == "EU" --> write to EU-West Primary
  |
  +-- user.region == "US" --> forward write to US-East Primary
  |                           [adds 90-100ms cross-region latency]
  |
  +-- user.region == "AP" --> forward write to US-East Primary
                              [adds 200ms+ cross-region latency]
```

The application-level routing is also where **write forwarding** happens. A US user whose request accidentally lands in EU-West (maybe they're traveling and connected to a EU VPN) has their write forwarded to US-East primary transparently. The user sees slightly higher latency but their data ends up in the correct primary.

---

### Health Checks and Automatic Region Removal

**Health checks** are automated probes that continuously test whether a region's load balancer and services are functioning. AWS Route 53, Cloudflare Load Balancing, and equivalent services run health checks from multiple geographic vantage points every 10–30 seconds.

When a region's health check fails (say, US-East's load balancer stops responding to HTTP health check requests), the geo-routing layer automatically removes US-East from the DNS rotation. Future DNS queries return EU-West or AP-Tokyo IPs instead. Existing connections to US-East will fail and clients will reconnect — resolving the new DNS to a healthy region.

**Health check design matters enormously**. A poorly designed health check causes false positives (removes a healthy region from rotation, causing unnecessary traffic shift and latency) or false negatives (fails to detect a genuinely broken region, leaving users hitting a failed endpoint).

Best practices:
- Health check the full request path, not just "can I reach the load balancer." A load balancer that is up but whose backend application servers are all down will pass a simple TCP health check but fail all real requests.
- Require multiple consecutive failures before removing a region (e.g., 3 consecutive failures 10 seconds apart = 30 seconds to removal). Single failure spikes are often transient.
- Health check from multiple vantage points simultaneously. If only one vantage point reports a region as down, it may be a network issue between that vantage point and the region, not a regional failure.

```
HEALTH CHECK FLOW:

Route 53 Health Checker (multiple vantage points):
  Vantage 1 (US)    --[GET /health]--> US-East LB  [200 OK]
  Vantage 2 (EU)    --[GET /health]--> US-East LB  [200 OK]
  Vantage 3 (AP)    --[GET /health]--> US-East LB  [FAIL]
                    wait 10 seconds
  Vantage 3 (AP)    --[GET /health]--> US-East LB  [FAIL]
                    wait 10 seconds
  Vantage 3 (AP)    --[GET /health]--> US-East LB  [FAIL]
                    --> 2/3 vantage points still healthy
                    --> no region removal (AP vantage point issue, not US-East)

ALL THREE FAIL:
  --> Route 53 removes US-East from DNS rotation
  --> All new DNS queries return EU-West or AP-Tokyo IPs
  --> Page Level 3 Critical alert
```

This geo-routing and health check infrastructure is the connective tissue that makes multi-region failover work. Without it, failover requires manual DNS changes that take hours. With it, failover is automatic and completes in DNS TTL + health check window (60 seconds + 30 seconds = ~90 seconds total).

---

Multi-region systems are not a single architectural decision — they are a sequence of deliberate tradeoffs made at each phase of a system's growth, driven by specific business triggers, legal requirements, and performance requirements.

For a social media API at Twitter scale: eventual consistency is correct for social content. Use write-central for non-regulated users, write-local for EU compliance. Serve 95% of read traffic from local replicas. Handle read-your-own-writes as a narrow 5-second exception after each write.

For authentication: never apply eventual consistency to session revocation. Synchronous replication to all regions on revocation, short-expiry JWTs, and per-region revocation lists in Redis give you both security and low-latency validation. The 250ms revocation latency cost is completely justified by the security alternative.

For news feeds: embrace lazy fan-out and per-region timeline caches with 30-second TTL. Hybrid fan-out — push for regular users, pull for celebrities — is the pattern that made Twitter, Instagram, and Facebook's feed systems work at scale. Celebrity fan-out would otherwise consume all your write capacity.

Evolve from single-region to multi-region in phases triggered by specific business requirements, not in anticipation of requirements you might have someday. Each phase introduces new failure modes — replica lag, untested runbooks, write conflicts, configuration drift — that must be understood before the phase is entered.

Monitor with six golden signals: per-region latency, replication lag, cross-region error rate, failover state, region health score, and traffic distribution. Run synthetic probes between all region pairs every 30 seconds to catch network degradation before real users experience it. Build an alerting hierarchy with three levels of urgency — warn to Slack, page on-call, critical all-hands.

Accept the organizational work that multi-region demands: defined service ownership with documented consistency contracts, follow-the-sun on-call with structured handoffs, GitOps to prevent configuration drift, and a quantitative cost justification to maintain with stakeholders. Know GDPR and PIPL at the architectural level — data residency is a first-class design constraint, not an afterthought.

The staff-level difference is this: junior engineers design for scale. Staff engineers design for scale, cost, compliance, team capability, and operational reality simultaneously — and they make each decision explicit rather than leaving it implicit in the architecture.
# Chapter 36 — Part E: Multi-Region Systems
### Production Incidents, Security, Compliance, and Staff-Level Mental Models

> "A distributed system is one in which the failure of a computer you didn't even
> know existed can render your own computer unusable." — Leslie Lamport
> Multi-region takes that problem and multiplies it by the number of continents
> you deploy to.

---

## Table of Contents

1. Production Incidents: Five Real Failures That Shaped Multi-Region Practice
2. Security and Compliance in Multi-Region Systems
3. Staff-Level Mental Models for Multi-Region
4. One-Liners for Staff-Level Interviews

---

## 1. Production Incidents: Five Real Failures That Shaped Multi-Region Practice

---

### Why Study Real Incidents

Theory teaches you what can go wrong. Incidents teach you what actually does.
The five failures below each changed how their company builds systems. Every
one maps to a principle you should be able to articulate in a staff-level
interview.

The what is interesting. The why is important. The fix and the prevention
principle are what you will be asked about.

---

### Incident 1: GitHub's MySQL Split-Brain (2018)

#### The Setup — How GitHub's Database Was Arranged

GitHub, the code hosting platform used by tens of millions of developers, runs
MySQL as its primary relational database. As of 2018, GitHub used a classic
**active-passive** replication topology. One MySQL instance — the **primary** —
was in a US-East data center. Several replica instances were spread globally,
including one in a secondary US data center that was specifically designated as
the **standby primary**, meaning if the main primary died, the standby was the
one that should automatically take over.

The arrangement looks like this:

```
+------------------+          fiber link          +------------------+
|   US-East DC-1   |<--------------------------->|   US-East DC-2   |
|                  |                              |                  |
|  MySQL PRIMARY   |     writes flow to primary   |  MySQL STANDBY   |
|  (accepts reads  |----------------------------->|  (replica,       |
|   and writes)    |                              |   reads only,    |
|                  |     replication stream       |   ready to       |
|                  |----------------------------->|   promote)       |
+------------------+                              +------------------+
         |
         | replication (async)
         |
+------------------+
|  Global Replicas |
|  EU, APAC, etc.  |
|  (reads only)    |
+------------------+
```

The system also had an **HA (high availability) agent** — automated software
that monitored the primary's health and could trigger promotion of the standby
if the primary became unreachable.

**STONITH** stands for "Shoot The Other Node In The Head." Before promoting a
replica to primary, STONITH forcibly shuts down or isolates the old primary so
that two nodes can never both believe they are primary simultaneously. Think of
it as: before you crown a new king, make absolutely sure the old king is dead.
The lack of properly working STONITH is exactly what caused this incident.

#### What Happened — 43 Seconds That Broke Two Hours

On a routine maintenance window in October 2018, GitHub engineers were doing
fiber work that involved briefly interrupting the physical cable connecting
US-East DC-1 and US-East DC-2. The interruption was planned and expected to
last roughly 60 seconds.

The HA agent in DC-2 noticed that it could no longer reach the primary in DC-1.
From DC-2's perspective, the primary was dead. The HA agent did what it was
configured to do: it began the promotion sequence to make the DC-2 standby the
new primary.

The promotion happened. DC-2's MySQL instance became the new primary and started
accepting writes.

Forty-three seconds later, the fiber came back up. DC-1's MySQL instance was
still running. It had never crashed. It had never received a shutdown command.
It came back online, looked at its own state, saw that it was still configured
as primary, and resumed accepting writes.

Now there were two primaries.

```
+------------------+                              +------------------+
|   US-East DC-1   |   fiber restored at t=43s   |   US-East DC-2   |
|                  |<--------------------------->|                  |
|  MySQL PRIMARY   |                              |  MySQL PRIMARY   |
|  (STILL thinks   |                              |  (promoted at    |
|   it's primary,  |                              |   t=10s,         |
|   accepting      |                              |   also accepting |
|   writes)        |                              |   writes)        |
+------------------+                              +------------------+
        |                                                  |
        | some writes                            other writes
        | go here                                go here
        v                                                  v
+---------------------------------------------------------------+
|   APPLICATION LAYER: routing traffic to BOTH "primaries"      |
|   Split-brain state: data diverging with every passing second |
+---------------------------------------------------------------+
```

This is **split-brain**: two nodes both acting as the authoritative source of
truth simultaneously, with no mechanism reconciling them.

#### The Damage — 2 Million Rows Out of Sync

The split-brain state persisted for approximately two hours before GitHub's
on-call team recognized what was happening and stopped writes to both instances.
In those two hours:

- GitHub's application was routing different write traffic to the two different
  "primaries." Some users' data was going to DC-1. Other users' data was going
  to DC-2.
- When writes stopped: approximately **2 million rows** were out of sync between
  the two instances. Some rows existed only in DC-1. Others existed only in DC-2.
  Others existed in both but with conflicting values.
- GitHub engineers had to write a **custom reconciliation job** — software that
  went row by row through the conflict set, applied business rules to determine
  which version was "correct," and resolved each conflict manually.
- Total incident duration: **24+ hours** of degraded or inconsistent service
  while the reconciliation ran.

#### Root Cause — STONITH Was Not Working

The HA agent promoted the standby without actually confirming that the original
primary was shut down. The STONITH step was configured in the system, but due
to a misconfiguration in the fencing mechanism, the command to force DC-1's
MySQL instance into read-only mode was never successfully delivered before
promotion completed.

The HA agent did not wait for confirmation that the fence had succeeded. It
assumed the fence worked and promoted anyway.

This is a pattern seen in many split-brain incidents: the safety check exists,
but it does not block progress if it fails. It is like a car safety system that
displays a warning but does not prevent you from starting the engine.

#### The Fix — Slow Down Promotion, Verify Before Accepting Writes

GitHub's fix had three parts:

**Part 1: Proper STONITH with blocking confirmation.** Before the new primary
accepts any writes, it must receive a positive confirmation that the old primary
has been forced into read-only mode via a separate control path (not the same
fiber link that was interrupted). If that confirmation never arrives, the
promotion is aborted.

**Part 2: Post-promotion validation gate.** After promotion, the new primary
runs a validation check: confirm that the old primary is not responding to write
traffic. Only after this gate passes does the new primary open to application
writes.

**Part 3: Raise the promotion threshold.** Changed from "1 consecutive health
check failure triggers promotion" to "5 consecutive health check failures over
30 seconds triggers promotion." This prevents promotions triggered by momentary
blips — like a 43-second fiber interruption.

#### Prevention Principle: One Failed Failover Beats Split-Brain

The core lesson GitHub encoded into their culture and runbooks:

> **Prefer a failed failover over a split-brain.**

A failed failover means your service is unavailable for a few minutes. That is
painful but recoverable. A split-brain means you have two diverging databases,
and recovery takes days. The asymmetry is enormous. Being slow to promote is
not a bug — it is a safety feature.

The second lesson: **test failover quarterly with chaos engineering.** If you
never intentionally cause the failure in a controlled environment, you do not
know if your STONITH actually works. GitHub now runs quarterly drills where they
deliberately kill the primary during low-traffic windows and verify that the
promotion completes correctly and the old primary is properly fenced.

---

### Incident 2: Cloudflare Global Outage via BGP Misconfiguration (2019)

#### The Setup — What Anycast Is and Why Cloudflare Uses It

Cloudflare acts as a CDN and reverse proxy for millions of websites. Its
architecture depends on **Anycast routing**: the **same IP address is announced
by all 193+ Cloudflare data centers simultaneously**. BGP (**Border Gateway
Protocol**) routes each user's packet to the nearest PoP automatically.

```
User in Tokyo    --> BGP --> Cloudflare Tokyo PoP
User in Frankfurt --> BGP --> Cloudflare Frankfurt PoP
User in São Paulo --> BGP --> Cloudflare São Paulo PoP

All three hit the SAME destination IP. BGP picks the nearest PoP per user.
```

This gives Cloudflare automatic geographic load balancing. It also means BGP
is Cloudflare's most critical control plane. If BGP routing breaks, Cloudflare
does not exist — for any user, anywhere.

#### What Happened — One Regex Broke the Internet for 30 Minutes

On July 2, 2019, a Cloudflare engineer pushed a new BGP routing policy. The
policy contained a regex (a pattern-matching expression) that was supposed to
filter certain route announcements. The regex had a bug: it caused the system to
advertise an overly specific route prefix — a `/20` network block instead of the
correct `/19`.

In BGP, more specific routes win. A `/20` beats a `/19`. When Cloudflare
advertised the incorrect `/20`, routing tables globally began sending traffic
in unexpected directions. Cloudflare's traffic dropped **82% globally within
27 minutes** of the push.

The cascade:

```
Bad BGP config pushed to ALL 193+ data centers simultaneously
  |
  v
Traffic routing breaks globally
  |
  v
Cloudflare customers (Discord, Shopify, Fitbit) unreachable
  |
  v
Cloudflare's OWN INTERNAL TOOLING goes down
(deployment tools also route through Cloudflare)
  |
  v
Engineers cannot reach deployment systems to push the revert
  Recovery takes longer than it should have
```

This is a classic **self-referential failure**: the outage broke the tooling
needed to fix the outage. The control plane depended on the thing it just
broke.

#### Root Cause — No Staged Rollout for Infrastructure Changes

Two separate failures compounded each other:

First, the regex bug itself — a technical mistake in the routing policy config.

Second, and more important: **there was no staged rollout mechanism for BGP
changes.** The configuration was pushed to all 193+ data centers simultaneously.
If it had been pushed to 1% of data centers first, the impact would have been
contained to a tiny fraction of users, and the error would have been visible
before global deployment.

There was no canary deployment for BGP changes. There was no automatic rollback
triggered by traffic drops. There was no human sign-off gate after 1% deployment.

#### The Fix — Staged Rollout, Automatic Revert, Human Gates

Cloudflare rebuilt their BGP change deployment process:

| Step | Old Process | New Process |
|------|-------------|-------------|
| Deployment scope | All PoPs simultaneously | 1% of PoPs |
| Monitoring window | None | 30 minutes post-deploy |
| Next stage gate | None | Human approval required |
| Subsequent stages | N/A | 10%, 25%, 50%, 100% |
| Auto-revert trigger | None | Traffic drop > 20% |
| Human sign-off | None | Required for Anycast route changes |

They also invested in making their internal tooling resilient to Cloudflare
network outages — using separate network paths that bypass the Anycast
infrastructure for control plane operations.

#### Prevention Principle: Canary Deploys Are Not Optional for Infrastructure

The lesson scales beyond BGP. Any time you are making a change that has a
**global blast radius** — meaning a bug in the change simultaneously breaks
things everywhere — you need a staged rollout. Period.

The staff-level framing: in a multi-region system, your control plane changes
(configuration, routing policy, schema migrations, feature flags) can cause
outages that are just as damaging as data plane failures. Canary deploys apply
to infrastructure changes, not just application code.

The corollary: **your control plane tooling must be resilient to the outage you
might cause with it.** If pushing a bad config breaks the tooling you need to
push the fix, you have a serious problem. Design your deployment and rollback
infrastructure to work even when the primary path is broken.

---

### Incident 3: DynamoDB Global Tables Replication Lag (Amazon Merchant, 2020)

#### The Setup — Active-Active Across Three Regions

**DynamoDB Global Tables** is Amazon's managed active-active database offering.
You configure a DynamoDB table to exist in multiple AWS regions simultaneously.
Writes can go to any region, and DynamoDB handles the replication to all other
regions. Under normal conditions, replication lag is under one second.

A large Amazon merchant used Global Tables across three regions:
`us-east-1`, `eu-west-1`, and `ap-northeast-1`. The architecture was designed
to give global users fast write performance. An EU user adding an item to their
cart wrote to `eu-west-1`. A US user wrote to `us-east-1`. DynamoDB replicated
the changes across regions asynchronously.

The merchant's application made a critical assumption: **replication lag is
always under one second.** This assumption was baked into every part of the
inventory and cart logic.

#### What Happened — A Promotion Exposed the Assumption

The merchant ran a major promotional campaign. During peak promotional traffic,
`us-east-1` was receiving over **100,000 writes per second** as US users added
items to their cart, claimed discount codes, and deducted inventory.

Under this burst load, DynamoDB's replication from `us-east-1` to `eu-west-1`
fell behind. Significantly behind. Replication lag grew from the normal sub-1-
second to **15 to 20 minutes**.

```
NORMAL conditions (light traffic):
  Write to us-east-1 at T=0:00
  Replicated to eu-west-1 at T=0:00.7   (lag: 0.7 seconds)
  Replicated to ap-northeast-1 at T=0:01 (lag: 1 second)

BURST conditions (100K WPS promotional traffic):
  Write to us-east-1 at T=0:00
  Replicated to eu-west-1 at T=15:00    (lag: 15 MINUTES)
  Replicated to ap-northeast-1 at T=18:00 (lag: 18 MINUTES)
```

While the lag was 15 minutes, EU users reading from `eu-west-1` were seeing
data that was 15 minutes old. For cart reads, this was annoying but not
catastrophic. For inventory checks, it was financially catastrophic.

Here is what happened to inventory:

```
T=0:00   - Item X: 500 units in inventory (correct in us-east-1)
T=0:01   - US user buys 1 unit -> inventory: 499 in us-east-1
           (NOT YET replicated to eu-west-1)
T=0:30   - EU user checks inventory -> eu-west-1 says: 500 units available
           (stale! actual stock is 499 or less)
T=0:31   - EU user buys 1 unit -> eu-west-1 thinks 499 remain
           But us-east-1 may already be at 400 units sold
           ...
T=15:00  - Replication catches up to eu-west-1
           eu-west-1 discovers inventory is actually at -47 (oversold)
```

Thousands of EU users bought items that were already out of stock, because
inventory checks were reading 15-minute-old data. The merchant had to cancel
and refund a significant number of orders post-event, with corresponding
customer service costs and trust damage.

#### Root Cause — Assuming Replication Lag Is a Constant, Not a Variable

The application was designed around a best-case assumption about replication
lag. In distributed systems, this is one of the most common architectural
mistakes: **designing for the happy path instead of the worst case.**

The replication SLA of "under one second" is correct under normal load. It is
not a guarantee under burst load. The merchant had never tested what replication
lag looked like at 100K writes per second, because they had never had a
promotion at that scale before.

#### The Fix — Route Inventory Checks to the Source of Truth

The fix distinguished between operations that could tolerate stale data and
operations that could not:

**Operations that tolerate eventual consistency (read from local replica):**
- Displaying cart contents to the user
- Product catalog browsing
- User profile reads

**Operations that require strong consistency (read from primary region):**
- Inventory availability check before purchase confirmation
- Coupon/discount code validation (prevent double-use)
- Account balance checks for store credit

```
EU User wants to buy Item X:
  |
  v
Cart display:   read from eu-west-1 replica  <-- stale OK, fast
  |
  v
Inventory check: read from us-east-1 PRIMARY <-- must be fresh, cross-region call
  |
  v
Confirm purchase: write to us-east-1 PRIMARY <-- single source of truth
```

Additional fixes:

- **Replication lag monitoring**: alert when lag > 3 seconds, page on-call when
  lag > 30 seconds, with a documented runbook for each threshold.
- **Oversell buffer**: allow up to 5% oversell as a safety valve (handle refunds
  gracefully rather than blocking purchases and losing the sale entirely).

#### Prevention Principle: Know Your Lag Under Burst, Not Just Normal

The test you need to run before going live with any eventually consistent
system: **what is the replication lag at 10x your expected peak load?** If you
do not know the answer, you do not know your actual consistency guarantees.

The design rule: **never make financially critical decisions on replica data.**
Inventory decisions, balance checks, coupon usage validation, order confirmation
— all of these must read from the authoritative source. The small latency cost
of a cross-region read for these operations is vastly cheaper than the
operational cost of canceling thousands of orders.

---

### Incident 4: Shopify Region Migration Data Loss (2021)

#### The Setup — Migrating Merchants for GDPR Compliance

Shopify, the e-commerce platform, needed to migrate a set of European merchants
from their US-East data center to a new EU-West region to comply with GDPR data
residency requirements. The migration plan was conceptually straightforward:

```
Step 1: Pause writes for merchant X
Step 2: Export merchant X's data from US-East
Step 3: Transfer data to EU-West
Step 4: Import data into EU-West database
Step 5: Switch merchant X's write path to EU-West
Step 6: Resume writes on EU-West
```

This is called a **lift and shift with write quiesce** — you quiet the old
location, move the data, and start up in the new location. The challenge is
ensuring that no writes happen during the quiesce window, because any writes
during that window will be lost when the destination database is loaded from
the snapshot taken before those writes.

#### What Happened — Writes Bypassed the Pause Mechanism

The migration script had a bug. The "pause writes" mechanism worked by removing
the merchant from the load balancer routing table. From that point forward, user
HTTP requests would not reach the merchant's write handlers. The script treated
this as "writes paused" and immediately began the data export.

The problem: **not all writes go through the load balancer.**

Shopify, like most large platforms, runs a large number of background jobs:
order fulfillment updates, automated email sending, inventory sync from third-
party apps, scheduled report generation. These background jobs wrote directly to
the database via internal service calls that bypassed the load balancer
entirely.

For approximately **4 minutes** after the "write pause" was declared, background
jobs continued writing to the US-East database. Meanwhile, the data export and
transfer to EU-West proceeded based on the snapshot taken before those 4 minutes
of writes.

When the EU-West import completed, the database was loaded with the
pre-4-minute snapshot. When Shopify switched writes to EU-West, the 4-minute
window of writes from US-East was gone. Those writes had never made it into the
EU-West database.

```
Timeline:
T=0:00  - Merchant removed from load balancer (writes "paused")
T=0:00  - Data export begins from US-East database snapshot
T=0:00  - Background jobs continue writing to US-East directly  <-- BUG
T=0:04  - Migration script detects export done, begins transfer
T=0:04  - Background jobs still writing to US-East              <-- BUG
T=0:10  - Transfer complete, import to EU-West begins
T=0:10  - Background jobs still writing to US-East              <-- BUG
T=0:15  - EU-West import complete
T=0:15  - Script switches writes to EU-West
T=0:15  - US-East write path removed
         4 minutes of background job writes (T=0:00 to T=0:04)
         are now permanently orphaned in US-East
         They were never in the EU-West snapshot
         They are now inaccessible
```

**2,311 orders** placed during those 4 minutes were permanently lost. Merchants
had confirmed order emails. Customers had payment charges. There were no
corresponding records in the database.

#### The Damage — Reconciliation by Credit Card Statement

The reconciliation process was labor intensive. Engineers and support staff
had to match credit card transaction records against missing order IDs, manually
reconstruct order records from payment processor logs, and contact affected
customers. The process took several days.

Beyond the direct cost, the incident exposed a broader vulnerability: the
write-pause mechanism was not what Shopify had thought it was. They had believed
removing a merchant from the load balancer was equivalent to stopping all writes.
It was not.

#### Root Cause — Trusting Application-Layer Controls for Data-Safety Operations

The root cause was an architectural assumption: that the load balancer was the
single chokepoint for all writes. In reality, Shopify's system had multiple
write paths, and the "write pause" only covered one of them.

This is a common failure mode in large systems: **the application grows multiple
write paths over time**, and the original assumptions about single-chokepoint
control become false. Nobody updated the migration runbook to reflect that
background jobs wrote directly to the database.

#### The Fix — Database-Level Write Gates and Checksum Validation

The new migration procedure has six steps, each of which must complete and be
validated before the next begins:

```
Step 1: Set merchant to READ-ONLY at the DATABASE LEVEL
        (not just load balancer removal — actual DB-level write block)

Step 2: Wait 60 seconds and verify ZERO write attempts occurred
        (monitor DB write counters; if any writes attempted, abort)

Step 3: Export data snapshot from now-quiesced database

Step 4: Transfer to EU-West
        Verify: source row count == destination row count
        Verify: source checksum == destination checksum
        (row count alone is insufficient; checksums catch data corruption)

Step 5: Switch write path to EU-West
        Verify: writes are flowing to EU-West (monitor write counters)

Step 6: Remove US-East write path ONLY after step 5 verified
```

The critical change: **write quiesce is now enforced at the database layer,**
not the application layer. No matter what path a write takes — HTTP request,
background job, direct database call — the database will reject it during the
quiesce window.

#### Prevention Principle: Use Database-Level Controls for Data-Safety Operations

Never trust application-layer controls for operations that require data safety
guarantees. Application layers have multiple paths, and you rarely know all of
them. Database-level controls are authoritative.

The second lesson: **checksums, not row counts.** Two tables can have identical
row counts while containing completely different data (imagine rows that were
updated vs. deleted-and-reinserted). A matching checksum is a much stronger
guarantee of data equivalence.

---

### Incident 5: Stripe's Double-Charge Due to Clock Skew (2022)

#### The Setup — Idempotency Keys and Payment Deduplication

Stripe, the payments processing platform, runs in **active-passive** mode across
US-East and US-West. Under normal conditions, US-East handles all writes. If
US-East has an issue, traffic fails over to US-West.

Stripe's payment processing is designed to be **idempotent** — meaning you can
safely retry a payment request multiple times, and it will only be charged once.
This is critical because networks are unreliable: a mobile client might send a
payment request, not receive the response, and retry. Without idempotency, the
customer gets charged twice.

The mechanism: every payment request includes an **idempotency key** (a unique
string generated by the client). Stripe stores a log of processed idempotency
keys. Before processing a payment, Stripe checks: "Have I seen this key before?"
If yes, return the original response. If no, process and store.

The deduplication window was configured as: **"reject as duplicate if the same
idempotency key arrives within 5 minutes of the original."** The 5-minute check
used wall-clock timestamps.

#### What Happened — Clock Skew Broke the 5-Minute Window

An NTP (Network Time Protocol) synchronization failure caused US-West servers
to drift ahead of the authoritative time source. By the time the issue was
detected, US-West's clocks were running **8 seconds ahead** of US-East.

Normally 8 seconds is trivial. But here is how it broke the deduplication logic:

```
The failure mode for payments near the 5-minute deduplication window edge:

East processes payment at T=4:55 (East time), stores that timestamp.
Retry arrives at West. West's clock reads T=4:47 (8 seconds behind East).

West checks: "original timestamp is T=4:55, my current time is T=4:47"
West sees: the original timestamp is 8 seconds IN THE FUTURE from its perspective.
West concludes: "this key cannot exist yet — must be a new payment."
West PROCESSES the payment.
Double charge.

The same 8-second skew causes East-timestamped records near the window
boundary to appear as future events from West's perspective, bypassing
the entire deduplication check.
```

Approximately **1,400 customers were double-charged** over a 3-hour window
before the issue was detected.

The damage: all double charges were caught and refunded within 24 hours through
automated reconciliation. No merchant fraud. But significant customer trust
impact and a high volume of customer support escalations.

#### Root Cause — Wall-Clock Timestamps for Ordering in a Distributed System

Two root causes:

First: **NTP sync failure** — a server configuration issue caused US-West nodes
to drift off authoritative time. This was a monitoring gap: there was no alert
for clock skew beyond a certain threshold.

Second, and more fundamental: **the idempotency system used wall-clock
timestamps for ordering**. Wall clocks in distributed systems are unreliable
for ordering events. They can drift, jump backwards (when NTP corrects a
forward drift), or be slightly inconsistent across machines. Using them for
deduplication logic creates a window of failure whenever clocks disagree.

#### The Fix — Logical Clocks and Cross-Region Idempotency

Stripe's fix had four parts:

**Part 1: Replace wall-clock timestamps with database-sequence-number-based
ordering.** Each idempotency key entry is assigned a monotonically increasing
sequence number by the database. Comparisons use sequence numbers, not wall-
clock times. Sequence numbers cannot skew.

**Part 2: NTP monitoring as a required production signal.** Automated alerting:
if any server's clock drifts more than 50 milliseconds from the authoritative
NTP source, trigger a page. This is now considered as important as CPU and
memory monitoring.

**Part 3: Extended the deduplication window** from 5 minutes to 24 hours. This
makes the system more tolerant of longer outages where retries might come in
after an extended gap.

**Part 4: Cross-region idempotency check.** Before processing any payment,
check the idempotency log in **both** US-East and US-West, regardless of which
region is currently active. This prevents the scenario where a key was logged
in one region but not yet replicated to the other.

```
New idempotency check flow:
  Payment arrives with idempotency_key="pay_abc123"
               |
               v
  Check US-East log for key  AND  Check US-West log for key
  (parallel reads to both regions)
               |
               v
  If found in EITHER region: return cached response (deduplicated)
  If not found in EITHER region: process payment, write to both regions
```

#### Prevention Principle: Never Use Wall Clocks for Ordering in Distributed Systems

This is one of the most important principles in all of distributed systems:

> **Wall clocks are not safe for ordering or deduplication in distributed
> systems. Use logical clocks, sequence numbers, or database-generated
> monotonic identifiers.**

Logical clocks (Lamport timestamps, vector clocks) capture event ordering
without depending on physical time. Database sequence numbers are guaranteed
monotonically increasing by the database engine. Wall clocks can lie.

The corollary: **clock skew monitoring is a required production signal.** If
you are running distributed systems and you do not have an alert on NTP
synchronization health, you have a gap in your observability. Add it. Today.

---

## 2. Security and Compliance in Multi-Region Systems

---

### The Expanded Attack Surface

Think about defending a medieval castle. The more gates your castle has, the
more places an attacker can try to get in, and the more people you need guarding
the walls. A castle with one gate is much easier to defend than one with twenty.

Multi-region systems are like building twenty gates into your castle. Every
region is a new entry point. Instead of one perimeter to defend, you have N
perimeters, one per region. Every one of those entry points needs the same level
of security as your original one — or you have created a new vulnerability.

The specific attack surface expansions that multi-region introduces:

**TLS certificates.** Every region must have valid TLS certificates for your
domain. Certificate expiry in any single region causes an outage in that region.
With five regions, you have five certificates to rotate. Certificate management
must be automated and centralized. Manual rotation is a time bomb.

**API keys and secrets.** Your application secrets (database passwords, API
keys for third-party services, signing keys for tokens) must be available in
every region. How do you get them there? How do you rotate them? If you
distribute secrets manually — copying `.env` files to servers — you will have
secrets that drift out of sync across regions and rotation events that
miss some servers.

**Firewall rules.** Every region has its own network perimeter (security groups,
VPC ACLs, firewall rules). If these are not identical (or intentionally
different for documented reasons), you have **configuration drift**: security
gaps in one region that do not exist in another. An attacker who discovers
the gap will exploit it.

**Audit trails.** In a single-region system, all access logs are in one place.
In a multi-region system, access logs are distributed. Correlating a security
incident across five regions' worth of logs is significantly harder. You need
centralized log aggregation.

---

### Secrets Management at Multi-Region Scale

The naive approach: copy secrets to each region's servers manually. This fails
because rotations in one region do not propagate, different regions end up with
different versions of the same secret, and there is no audit trail.

The correct approach: **secrets manager with automatic regional replication**.

```
+------------------+   auto replication   +------------------+
|  Secrets Manager |-------------------->|  Secrets Manager |
|  us-east-1       |                     |  eu-west-1       |
|  (primary)       |                     |  (replica)       |
+------------------+                     +------------------+
        |                                        |
        | local read (fast)                      | local read (fast)
        v                                        v
+------------------+                     +------------------+
|  us-east-1 app   |                     |  eu-west-1 app   |
+------------------+                     +------------------+
```

**AWS Secrets Manager** replicates secrets to secondary regions automatically.
Rotate once in the primary; all replicas pick up the new value. **HashiCorp
Vault** provides the same model for multi-cloud or on-premises environments.

The principle: secrets management infrastructure needs the same HA, replication,
and monitoring discipline as your primary database.

---

### Data Residency and Access Controls for GDPR

**GDPR** requires EU personal data to be stored and processed within the EU.
For a multi-region system, this means:

- EU user data stored in EU-region databases only (not replicated to US)
- Non-EU IAM roles explicitly denied access to EU data stores
- Every access to EU user data logged for audit: timestamp, identity, justification

AWS implementation:

**IAM policy isolation** — deny all US-region IAM roles from accessing EU-region
S3, DynamoDB, and RDS resources at the policy level.

**Network isolation** — EU-region VPC has no peering to US-region VPC for
data-bearing resources. Cross-region access goes only through logged API gateways.

**Audit logging** — every EU data store read captured in CloudTrail, forwarded
to centralized compliance logging. Cannot be bypassed by application code.

```
+---------------------------+       +---------------------------+
|    EU-West Region         |       |    US-East Region         |
|  EU User Data (S3, RDS)   |       |  US User Data (S3, RDS)   |
|  IAM: DENY non-EU roles   |       |  IAM: DENY non-US roles   |
|  VPC: no US peering       |       |                           |
+---------------------------+       +---------------------------+
           |   only via logged API gateway    |
           +----------------------------------+
```

---

### Zero-Trust Between Regions

In a traditional perimeter security model, traffic arriving from your own
EU-West servers is considered safe. This breaks in multi-region: a compromised
server in one region can impersonate internal services and make calls to other
regions that the perimeter model accepts without question.

**Zero-trust** principle: "never trust, always verify." Every service
authenticates every request it receives, regardless of source. **Mutual TLS
(mTLS)** is the standard implementation — both sides verify each other's
certificate before the connection proceeds.

```
Without mTLS: Client authenticates server. Server trusts client because
              it's on the internal network. Compromised internal server
              can impersonate anything.

With mTLS:    Client authenticates server cert AND server authenticates
              client cert. A compromised server cannot impersonate another
              service because it lacks that service's client certificate.
```

Google's **BeyondCorp** initiative (post-2009 Operation Aurora attack) and
Cloudflare (uses its own Zero Trust product internally) are the canonical
production examples. For inter-region calls, mTLS means a compromised node
in one region cannot forge trusted API calls to another region.

---

## 3. Staff-Level Mental Models for Multi-Region

---

### What a Mental Model Is and Why These Matter

A mental model is a compressed way of reasoning about a category of problems.
Good engineers carry a library of them. When a multi-region problem appears in a
design review or interview, the right mental model lets you reason quickly and
correctly without re-deriving everything from scratch.

The five below are the tools experienced engineers actually use. Articulate them
clearly with a specific example and you are thinking at the staff level.

---

### Mental Model 1: Every Region Is Both a Resource and a Liability

More regions means lower latency for more users and more redundancy. Those are
the **resource** side. The **liability** side gets less attention:

- Every region is a new place for a bug to live
- Every region is a new attack surface to defend
- Every region adds operational cost: infrastructure, monitoring, on-call
- Every region adds complexity to deployments, testing, and incident response
- Every region adds latency to any operation that coordinates across regions

**Every region you add must be justified by resource value exceeding liability
cost.** "More regions is better" is intern-level thinking. "These regions serve
these users with this latency improvement, justified by this business requirement"
is staff-level thinking.

When someone says "we should add a region" in a design review, the staff
question is: "What does adding a region solve that a CDN and read replicas
cannot?"

---

### Mental Model 2: Consistency Is a Product Decision, Not a Technical One

"Eventual consistency is more scalable" is technically true and completely
irrelevant if the business cannot tolerate stale data for the field in question.

Correct process:

```
Business: "user profile can be 10 seconds stale, payment state cannot be stale"
Engineer: maps each requirement to a consistency model and implements it
Engineer: documents the choices and gets explicit sign-off from data owners
```

What actually happens in many teams:

```
Engineer picks eventual consistency (easier to build)
Business launches, discovers payment state was eventually consistent
Discovery happens during an incident, not a design review
Emergency rearchitecture follows
```

The staff-level principle: **make consistency explicit for every data type,
document it, and get stakeholder sign-off.** The engineer's job is to present
options with tradeoffs — the business decides. The Stripe incident happened
because nobody explicitly agreed that idempotency keys could be eventually
consistent across regions. They cannot be.

---

### Mental Model 3: The Blast Radius of Every Change Is Global

In a single-region system, a bad configuration deploy affects one region. Your
on-call engineer rolls it back. Recovery time: minutes. Affected users: a
fraction of your total user base.

In a multi-region system deployed simultaneously to all regions: a bad config
deploy affects everyone. Every user. Every region. At the same time. Recovery
time: as long as it takes to deploy the rollback globally, which takes longer
than the original deploy because you are now doing it under incident stress.

```
Single-region deploy gone wrong:
  Deploy -> 1 region broken -> rollback -> 1 region fixed -> done
  Blast radius: 1 region

Multi-region simultaneous deploy gone wrong:
  Deploy -> ALL regions broken -> rollback to all regions -> recovery complete
  Blast radius: global
  Recovery time: 3x to 10x longer than single-region
```

The mitigation is **staged deploys with automatic rollback**:

```
Stage 1: Deploy to canary region (1-2% of traffic)
         |
         | Wait 15-30 minutes
         | Monitor: error rate, latency, business metrics
         |
         v
Stage 2: Deploy to 10% of regions
         |
         | Wait 15-30 minutes
         | Same monitoring
         |
         v
Stage 3: Deploy to 50% of regions
         |
         v
Stage 4: Deploy to 100%

At ANY stage: if error rate increases > threshold,
automatic rollback to previous version in affected regions.
Human sign-off required to continue past each stage gate.
```

This applies to: application code, configuration changes, database schema
migrations, infrastructure changes, routing policy changes. There is no
category of change in a multi-region system that is safe to deploy globally
and simultaneously without canary validation.

---

### Mental Model 4: Distributed Systems Do Not Fail Cleanly

Single-region mental model of failure: the region is UP or it is DOWN. Binary.
You build for it: health check fails, remove from load balancer, redirect
traffic.

Multi-region reality: **failure is partial, asymmetric, and gradual.** Real
production failures look like:

- "Region is responding to 73% of requests normally, the other 27% are getting
  500 errors, but only for users in the US-West region whose requests are
  hitting a specific availability zone"
- "The database in EU-West is accepting reads fine, but writes are silently
  queued and not being committed due to a transaction log issue"
- "The control plane for the region is unreachable, but the data plane is
  serving traffic normally — we can't deploy but existing services are running"
- "Replication from US-East to EU-West is processing at 20% of normal throughput
  due to a network degradation on the inter-region backbone"

None of these are binary. None of them trigger a clean failover. All of them
require nuanced responses.

The design implication: **every service must have graceful degradation modes for
partial failures, not just binary up/down handling.** This means:

- Circuit breakers that track partial failure rates, not just complete failures
- Read paths that can fall back to stale cache data when the live database is
  degraded but not fully down
- Write paths that can queue to a local buffer when the primary region is
  reachable but slow
- Monitoring that surfaces partial failures with sufficient granularity to
  distinguish them from normal variability

The staff-level question to ask in design reviews: "What does this service do
when the cross-region call succeeds 70% of the time instead of 99.9%? Is the
response 'error' or 'degraded but functional'?"

---

### Mental Model 5: Treat the Inter-Region Network as an Unreliable WAN

When your servers are in the same data center, they communicate over a local
network with latency measured in microseconds and packet loss measured in
fractions of a percent. Engineers build systems that implicitly assume this
reliability.

When your servers are in different regions, they communicate over the public
internet or peered backbone networks with latency measured in tens to hundreds
of milliseconds and periodic packet loss events. **The inter-region link is a
wide-area network (WAN), and it behaves like one.**

```
Same data center:
  Server A --> Server B
  Latency: 0.1-1ms
  Packet loss: near zero
  Reliability: very high

Different regions (cross-continent):
  Server A --> [internet or peered backbone] --> Server B
  Latency: 80-150ms
  Packet loss: occasional spikes during routing events
  Reliability: high but not "same data center" high
```

Design implications:

**Every inter-region call can fail.** Design every cross-region interaction with
retries, timeouts, and fallbacks. A function that calls another region must
handle the case where that call times out or returns an error. "It's our own
infrastructure" is not a sufficient reason to omit error handling.

**Minimize cross-region calls on the critical path.** Every inter-region call
adds 80-150ms of latency to your user-facing response time. Design write paths
that minimize how many cross-region round-trips are required to complete a user
operation. Batch cross-region work. Use async replication where consistency
requirements allow.

**Circuit breakers between regions.** If cross-region calls are failing at a
meaningful rate (e.g., 20% of calls), stop trying. A circuit breaker opens,
requests are served from local data (possibly stale) or degraded responses are
returned, and an alert fires. This prevents a degraded inter-region link from
cascading into a full regional outage.

```
Normal: 99.9% success rate
  App --> [cross-region call] --> remote region
  |
  v
Circuit: CLOSED (passing traffic)

Degraded: >20% failure rate
  App -X [cross-region call fails] -> remote region
  |
  | after N failures in M seconds:
  v
Circuit: OPEN (stop trying, serve fallback/stale data)
  Alert fires, on-call paged

Recovery: periodic probe to check if remote region recovered
  If probe succeeds: Circuit moves to HALF-OPEN (try real traffic)
  If real traffic succeeds: Circuit -> CLOSED (normal)
  If real traffic fails: Circuit -> OPEN again
```

---

## 4. One-Liners for Staff-Level Interviews

The following are exact phrasings that demonstrate staff-level thinking in a
system design interview. Practice saying them out loud until they are natural.
Each one signals that you understand the tradeoffs, not just the mechanics.

---

**On active-active vs. active-passive:**
> "We use active-passive by default and only move to active-active for services
> where conflict resolution is well-defined, tested, and operationally
> understood. Active-active sounds better on paper but it is meaningfully harder
> to operate correctly."

---

**On write path design:**
> "Every write that crosses a region boundary adds at least one cross-region
> round-trip — typically 80 to 150 milliseconds. I design write paths to
> minimize cross-region calls on the user-facing critical path. Async replication
> after the write completes is preferred over synchronous coordination before."

---

**On RPO and RTO:**
> "Our RPO and RTO are business decisions, not technical ones. I present the
> options with their cost and complexity tradeoffs and let the business decide.
> A 5-minute RPO costs one number. A 30-second RPO costs a significantly larger
> number. The business picks what they can afford and what they can justify to
> customers. I build what they choose."

---

**On failover testing:**
> "I test failover quarterly. If failover has not been tested in the last 90
> days, I do not believe it works. The GitHub MySQL incident happened precisely
> because STONITH was configured but never verified. Quarterly drills are not
> optional."

---

**On replication lag:**
> "We monitor replication lag 24/7 as a first-class production signal. If lag
> exceeds our normal threshold, we have an automated runbook: either reduce
> write throughput, switch financially critical reads to the primary, or page
> on-call to investigate. Discovering replication lag during an incident rather
> than before is how you end up with the DynamoDB merchant oversell problem."

---

**On consistency choices:**
> "I never pick a consistency level without first checking with the business
> owner of that data. 'Eventual consistency' on payment state is not a technical
> decision I get to make unilaterally. I present the options, they decide, and
> the decision is documented."

---

**On deployment:**
> "All deployments are staged: canary region first, then 10%, then 25%, then
> global. Automatic rollback triggers if error rate spikes beyond threshold at
> any stage. This applies to application code, configuration, infrastructure
> changes, and routing policy. The Cloudflare BGP incident happened because
> there was no staged rollout for an infrastructure change."

---

**On clock-based logic:**
> "I do not use wall-clock timestamps for ordering, sequencing, or deduplication
> in distributed systems. Logical clocks or database-generated sequence numbers
> only. Clock skew is a real production hazard and the Stripe double-charge
> incident is the textbook example of what happens when you use wall clocks for
> deduplication logic."

---

**On blast radius:**
> "Before I approve any change that touches global routing, global configuration,
> or global infrastructure, I ask: what is the blast radius if this change is
> wrong? If the answer is global, it goes through the staged rollout process
> regardless of how confident we are in the change."

---

**On partial failures:**
> "I design for the partial failure case, not the binary up/down case. A region
> that is responding to 70% of requests with extra latency is not the same as
> a region that is fully down. My circuit breakers, my monitoring, and my
> runbooks all distinguish between these cases. Treating partial failures as
> binary failures is how you make them worse."

---

*End of Chapter 36 — Part E*

*Next: Chapter 36 — Part F: Designing Multi-Region Systems from Scratch
(Trade-Off Framework for Staff-Level Design Reviews)*
# Chapter 36: Multi-Region Systems
## Part F: Calibration, Brainstorming, Exercises, and Quick Reference

---

This is the FINAL section of Chapter 36.

All brainstorming questions, homework exercises, and
reference material live here.

---

## 1. L5 vs L6 Calibration Table

The table below shows 12 interview dimensions.

For each one: what an L5 candidate typically says,
and what an L6 candidate says.

L6 answers are specific, numbers-grounded, and
trade-off-aware. L5 answers are plausible but thin.

---

**Dimension 1: When to go multi-region**

L5 answer:
- "When you need high availability and global users."

L6 answer:
- Start with the specific trigger: latency or availability?
- Latency: if P99 from a remote continent > 200ms
  and CDN/read replicas don't solve it.
- Availability: if SLA requires RTO < 15 minutes
  AND a single AZ failure is not sufficient protection.
- Multi-region adds 2.5–3× cost and serious operational
  complexity. Justify it with data, not intuition.
- Most systems below 10M users never need it.

---

**Dimension 2: Active-active vs active-passive choice**

L5 answer:
- "Active-active is better because all regions serve traffic."

L6 answer:
- Active-active is only appropriate when you have:
  (a) a conflict resolution strategy for your data model
  (b) data types that are CRDTs or append-only, OR
  (c) a business requirement that every region must accept writes
- For most relational / transactional systems:
  active-passive is the right default.
- Active-active for a payment ledger is dangerous
  without CAS or distributed locking.
- The cost of getting active-active wrong is silent
  data corruption, not just downtime.

---

**Dimension 3: Handling replication lag**

L5 answer:
- "Use async replication and accept eventual consistency."

L6 answer:
- You must categorize reads by staleness tolerance first.
- "Show my bank balance": read from primary. Never replica.
- "Show my post like count": async replica fine, lag < 5s ok.
- Read-after-write pattern: pass a replication position token
  (Postgres LSN or MySQL GTID) in a cookie or header.
  Route requests with that token to primary (or wait for replica
  to catch up) for the next 10–30 seconds after a write.
- Monitor replication lag with a heartbeat table:
  write a timestamp row to primary every second,
  read it from replica. Lag = now() - timestamp.
- Alert at > 10 seconds. Auto-failover reads to primary at > 30 seconds.

---

**Dimension 4: Failover — automatic or manual**

L5 answer:
- "Automatic failover is better because it's faster."

L6 answer:
- Automatic failover: faster (30–90 seconds) but risks split-brain
  if the primary is not truly dead (just slow or partitioned).
- Manual failover: slower (5–30 minutes, human in the loop)
  but eliminates split-brain risk.
- The right answer depends on RTO requirement:
  - RTO < 2 minutes → automatic (with STONITH mandatory)
  - RTO < 15 minutes → manual with runbook automation
- STONITH is non-negotiable for automatic failover.
  Without it, automatic failover will eventually cause split-brain.
- Most mature systems use automated detection + manual
  promotion, not fully automatic promotion.

---

**Dimension 5: Split-brain prevention**

L5 answer:
- "Use a quorum / majority vote to avoid split-brain."

L6 answer:
- Quorum is necessary but not sufficient.
- After detecting that primary is unreachable:
  Step 1: STONITH — fence the old primary (set it to read-only,
  or terminate it) BEFORE promoting the replica.
  Step 2: Promote replica only after STONITH confirmation.
- Without STONITH: even with quorum, the old primary
  may still accept writes from clients that haven't timed out yet.
- In practice: use a STONITH agent (AWS RDS instance stop,
  or revoke the DB security group rule) as the fence action.
- Also: reduce client connection timeout aggressively
  so clients fail fast and route to new primary.

---

**Dimension 6: Write latency in multi-region**

L5 answer:
- "Sync replication makes writes slower. Use async instead."

L6 answer:
- Quantify first: NYC to London RTT = ~75ms.
  Sync write to EU-West replica adds 75ms to every US write.
  At 5K writes/second: 5,000 × 75ms = unacceptable.
- Async replication is the right default for write latency.
- But: if you need RPO = 0 (zero data loss), sync is required
  for at least one replica.
- Semi-sync replication (one sync replica, rest async)
  is a common compromise: RPO = 0, write latency
  penalty = 1 × RTT (not N × RTT).
- For active-active: writes go to local region.
  Cross-region replication is async. Conflicts are deferred.

---

**Dimension 7: Data residency / GDPR compliance**

L5 answer:
- "Keep EU user data in EU. Use separate databases."

L6 answer:
- GDPR data residency is not just about storage.
  It covers: computation (no EU data processed outside EU),
  backups (EU backups must stay in EU),
  logs (EU user data in logs must be purged per retention policy).
- Implementation: partition by user_id region shard key.
  EU users → eu-west-1 primary. US users → us-east-1 primary.
  Routing layer must know the region of each user_id.
- Cross-region query problem: EU user paying US merchant.
  Resolve at the application layer, not the DB layer.
  The EU service calls the US service via an API call
  that does not transfer the raw EU row — it transfers
  only the derived transactional result.
- Audit log: every cross-region data access must be logged.
  GDPR auditors will ask for it.

---

**Dimension 8: CDC and replication for databases**

L5 answer:
- "Use read replicas for replication. It's built into most databases."

L6 answer:
- Read replicas: great for same-service reads.
  Not great for cross-service or cross-datastore replication.
- CDC (Change Data Capture) via the WAL (Postgres) or
  binlog (MySQL) is the right tool for cross-service replication.
  It is non-invasive: zero change to the application write path.
- Debezium → Kafka is the standard pattern:
  DB WAL → Debezium connector → Kafka topic
  → consumer services or regional replicas.
- Advantages: ordering guarantees, replay capability,
  fan-out to multiple consumers, works with schema changes.
- Key numbers: Debezium processes ~10K events/second
  on a single connector. At higher throughput: partition
  the Kafka topic by table or entity_id.
- Lag monitoring: track the Kafka consumer group offset lag
  for the regional replication consumer. Alert at > 5 seconds.

---

**Dimension 9: Cost of multi-region**

L5 answer:
- "Multi-region is more expensive because you're running more servers."

L6 answer:
- Compute: 3 regions × same fleet = 3× compute cost.
  Mitigation: use spot/preemptible instances for stateless
  workloads in non-primary regions (40–60% savings).
- Data transfer: AWS charges $0.02/GB for cross-region.
  At 1TB/day replication: $20/day = $600/month.
  At 10TB/day: $6,000/month — suddenly significant.
- Database: RDS Multi-AZ in 3 regions = 3× DB cost.
  Mitigation: use a global database (Aurora Global) which
  has a single billing unit for multi-region.
- Real multiplier: 2.5–3× total infrastructure cost.
- Always ask: "Can we achieve the same latency goal
  with CDN + regional read caches?" before committing
  to full multi-region. Often cheaper by 60–70%.

---

**Dimension 10: Monitoring a multi-region system**

L5 answer:
- "Use the same dashboards per region and compare them."

L6 answer:
- You need cross-region correlation, not just per-region metrics.
- Key metrics to track globally:
  - Replication lag per region (P50, P99, max)
  - Cross-region request latency (add trace IDs that span regions)
  - Region traffic split (is failover routing working?)
  - Write success rate per region (divergence from baseline = alarm)
- Synthetic probes: run a canary user in each region every 60 seconds.
  It performs a write in US-East and verifies the value is readable
  in EU-West within 5 seconds. This measures real replication lag
  from the user's perspective.
- Alert tiers:
  - Lag > 10 seconds: page on-call
  - Lag > 30 seconds: automatic action (reroute reads to primary)
  - Lag > 5 minutes: escalate to incident commander
- Centralized logging: ship all region logs to a single SIEM
  (Splunk or Elasticsearch in a "logging region").
  Do not rely on per-region log dashboards for incident response.

---

**Dimension 11: Configuration drift across regions**

L5 answer:
- "Use Terraform to keep regions in sync."

L6 answer:
- Terraform is necessary but not sufficient.
  Drift happens when:
  (a) engineers make manual hotfixes in one region
  (b) a Terraform run fails mid-way and is not retried
  (c) a service is upgraded in one region but not others
- Detection: run `terraform plan` on all regions in CI/CD.
  Any non-empty plan = drift detected → alert.
- Also: application-level config drift.
  Feature flags, Redis config, JVM flags, connection pool sizes.
  These often live outside Terraform.
  Use a config management tool (Ansible or Chef) for OS/app config.
- Enforce: policy-as-code checks (OPA or Sentinel)
  that block Terraform applies with per-region exceptions.
- Canary deploys: deploy to one region first.
  Wait 30 minutes. Promote to all regions.
  This catches drift that Terraform doesn't catch.

---

**Dimension 12: The first step to improve global latency**

L5 answer:
- "Add a region closer to the users."

L6 answer:
- Adding a region is usually the LAST step, not the first.
- Step 1: Measure where the latency is.
  Is it DNS resolution? TLS handshake? Time to first byte?
  Network transit? Or application processing time?
- Step 2: CDN for static assets and cacheable API responses.
  This alone can cut P99 latency by 60–80% for most apps.
  Cost: $500–$2K/month. No operational complexity.
- Step 3: Read replicas for database reads.
  Put a read replica in each major geography.
  Serve reads locally. Cost: 1 extra DB instance per region.
- Step 4: Edge compute (Lambda@Edge or Cloudflare Workers)
  for lightweight logic (auth, redirect, geo-routing).
- Step 5: Only if the above is insufficient AND latency
  is caused by write operations (not reads): add a full region.
- "Add a region" costs 2.5–3× and takes 3–6 months to operate safely.
  Exhaust the other options first.

---

## 2. Brainstorming Questions

20 questions across 4 themes.

Use these to practice before interviews.

Spend 20–35 minutes per question.

Write out your design before reading the hints.

---

### Theme A: Architecture and Replication Model Decisions

---

**Question 1: Fintech Multi-Region with GDPR**

**Scenario:**

- A fintech startup (Series B, 150 engineers, $2B GMV)
- Processes payments for US and EU customers
- 60% of users are in the US, 40% in EU
- Writes: 10K/second peak
- Reads: 200K/second peak
- EU requires GDPR compliance:
  EU user payment data must stay in EU

**Design task:**

Design a multi-region architecture. Specify:

1. Which model (active-passive / active-active / hybrid)?

2. Where each region's data lives.

3. How cross-region payments are handled
   (EU user paying a US merchant).

4. RTO/RPO targets and how you achieve them.

**Key tensions:**

- GDPR forbids EU payment data from leaving EU
- But EU user → US merchant transaction touches both regions
- Active-active is tempting but requires conflict resolution
  for a system where double-charging is catastrophic

**Hint to unlock after your attempt:**

Use a hybrid model:

- EU primary (eu-west-1) owns all EU user records
- US primary (us-east-1) owns all US user records
- No raw data crosses the border
- Cross-region payments: EU service calls US service
  via an internal API that exchanges only derived results
  (authorization code, amount, status) — not raw PII
- Each region is active-primary for its own users
- Each region has a passive standby for failover
- RTO: 2 minutes (automated), RPO: 30 seconds (semi-sync)

---

**Question 2: Real-Time Multiplayer Game**

**Scenario:**

- Game needs < 50ms write latency for all players globally
- Current: single region in us-east-1
- EU players: 150ms writes (unacceptable for a real-time game)
- AP players: 200ms writes (extremely bad)
- Game uses a room-based model:
  all players in one room connect to the same game server

**Design task:**

1. Design a multi-region architecture
   that achieves < 50ms writes for all players.

2. Which region hosts the "authoritative" game state
   for a given room?

3. What happens to a game room if its hosting region
   fails mid-game?

4. How do you route a new player to the right region
   when they join a room that's already in progress?

**Key tensions:**

- Rooms have one authoritative server (solves conflict problem)
- But if all players in a room are from different continents,
  someone will always have cross-region latency
- Failover for a live game room is very disruptive

**Hint to unlock after your attempt:**

- Room server in the region closest to the MAJORITY of players
- If a room has 6 players: 4 US, 2 EU → host in US-East
- The 2 EU players accept 75ms latency (better than 150ms baseline)
- On region failure: pause game, migrate room state to secondary region,
  resume. Players see a 2–5 second pause.
  Acceptable. Silent data loss is not acceptable.
- Client-side prediction + server reconciliation (like FPS games)
  compensates for the remaining latency.

---

**Question 3: Inventory Management Without Oversell**

**Scenario:**

- Global e-commerce platform
- "Nike Air Max, size 10, last pair in stock"
- Could be purchased simultaneously from US and EU
- You must not oversell

**Design task:**

1. Option A: centralize inventory writes to one region.
   What is the latency impact on EU purchase path?

2. Option B: active-active with conflict resolution.
   What conflict resolution strategy prevents oversell?
   Can CRDTs solve this?

3. Design an inventory system with:
   - < 5% oversell rate
   - < 300ms purchase latency globally

**Key tensions:**

- True inventory reservation requires a distributed lock
  or centralized authority
- CRDTs support increment/decrement but cannot enforce
  "stop at zero" without coordination
- Oversell is a business cost (not a correctness violation)
  so some approaches accept small oversell rates

**Hint to unlock after your attempt:**

- Inventory counts are a "PN-Counter CRDT" problem,
  but the boundary condition (floor at 0) breaks pure CRDT.
- For last-unit scenarios: use a "reservation token" system.
  Each unit has a unique token. Purchasing = claiming a token.
  Tokens are pre-distributed to regions proportionally.
  US-East gets 60% of tokens (matching traffic split).
  EU-West gets 40%.
  If EU region runs out of tokens: cross-region call for more.
- Oversell only happens if both regions claim the last token
  simultaneously (race condition window = replication lag).
  At 2-second lag and 10K writes/second:
  oversell rate < 0.001% for non-last-unit scenarios.
  For last-unit: explicit central lock is the only safe option.

---

**Question 4: Customer-Specific Data Residency in SaaS**

**Scenario:**

- SaaS analytics product
- Customer A: data must stay in US (contractual)
- Customer B: data must stay in EU (GDPR)
- Customer C: no restriction

**Design task:**

1. Design a multi-region architecture
   satisfying all three constraints in one system.

2. How does the routing layer know which customer's data
   goes to which region?

3. What happens when Customer A wants to query against
   Customer C's shared dataset?

4. How do you handle a Customer C tenant that is later
   acquired by a company requiring EU residency?

**Key tensions:**

- Multi-tenant SaaS: shared infrastructure per region
- But data residency is per-tenant, not per-region
- Cross-tenant queries (Customer A × Customer C) are common
  in analytics products (shared benchmarks, aggregated reports)

**Hint to unlock after your attempt:**

- Tenant metadata service: maps tenant_id → home region.
  This service is read-heavy, globally cached (TTL: 5 minutes).
  Update is rare (tenant migration is a multi-week process).
- Routing layer: API gateway reads tenant header/JWT claim,
  looks up home region, routes request.
- Cross-tenant query: Customer A (US) × Customer C (global).
  Option: replicate Customer C's anonymized/aggregated data
  to US-East for query federation. Raw data never leaves.
  Only summary tables cross regions.
- Tenant migration (Customer C → EU-only):
  It's a data migration, not a config change.
  Copy data to EU, verify, update routing, delete US copy.
  Typically a 2–4 week process with read-only period.

---

**Question 5: Migration from Single-Region to Multi-Region**

**Scenario:**

- Staff Engineer at a company migrating us-east-1 → multi-region
- Current: all services in us-east-1,
  Postgres primary, stateless API servers behind an ALB
- Goal: add eu-west-1, full active-passive
- RTO < 5 minutes, RPO < 30 seconds

**Design task:**

1. What do you migrate first?
   (Services vs. database vs. DNS vs. monitoring)

2. What are the top 3 things that can go wrong?

3. How do you test the failover before it's needed in production?

4. Define "done": what criteria must be met
   before you declare the multi-region setup production-ready?

**Key tensions:**

- Stateless services are easy to replicate
- Database is the hard part: replication setup, failover,
  and client reconnection all need testing
- Testing failover in production is risky
  but testing it on a shadow system may miss edge cases

**Hint to unlock after your attempt:**

- Migration order:
  1. Set up monitoring in eu-west-1 first (you need visibility before anything else)
  2. Set up the database replica (async, 30-second lag target)
  3. Deploy stateless API servers in eu-west-1 (point at us-east-1 DB for now)
  4. Configure Geo-DNS (but send 0% traffic to EU-West initially)
  5. Enable read routing for EU users to EU replica (reads only)
  6. Test failover in a maintenance window (full write promotion test)
  7. Declare production-ready
- Top 3 failure modes:
  (a) Application not handling DB hostname change on failover
  (b) Secrets/config not deployed to eu-west-1
  (c) DNS TTL too high (set to 60 seconds before testing)
- "Done" criteria:
  Automated failover test with < 5-minute RTO verified.
  Replication lag < 10 seconds at peak load verified.
  Runbook reviewed by second engineer.

---

### Theme B: Failure Handling and Recovery

---

**Question 6: Resolving a Live Split-Brain**

**Scenario:**

- Active-passive. US-East is primary. EU-West is standby.
- Monitoring detects US-East is down.
  Automated failover promotes EU-West to primary.
- 4 minutes later: US-East comes back online.
  It was a network blip. US-East was never truly dead.
- You now have two MySQL instances both believing
  they are primary.
- Both accepted writes during the 4-minute split-brain window.

**Design task:**

1. Walk through the exact steps to resolve this.
   Which writes do you keep? Which do you discard?

2. How long does full reconciliation take?

3. How do you communicate with users during this time?

4. Design 3 changes that would have prevented this.

**Key tensions:**

- You cannot "merge" two conflicting write histories
  without business logic (which record is correct?)
- For a payment system: every conflict requires manual review
- Time pressure: the longer split-brain persists,
  the more divergence accumulates

**Hint to unlock after your attempt:**

- Immediate action: fence US-East (set read-only) immediately.
  EU-West is now the de facto primary.
  Stop all new writes to US-East NOW.
- Reconciliation:
  Pull transaction logs (WAL/binlog) from both DB instances.
  Find the divergence point (last common GTID/LSN).
  All EU-West writes after divergence point: apply to US-East replica.
  All US-East writes after divergence point: review case by case.
  For payment records: match against payment processor's record.
  The payment processor is the source of truth. Not your DB.
- Expect 2–4 hours for reconciliation if 4,000+ rows diverged.
  For a payment processor: all affected users get an email.
- Prevention changes:
  (1) STONITH: fence US-East before promoting EU-West.
  (2) Conservative health check: require 5 consecutive failures
      (not 1) before triggering failover.
  (3) Automatic re-join as read-only: when US-East comes back,
      it automatically starts as a replica, NOT as a primary.

---

**Question 7: Partial Network Partition**

**Scenario:**

- US-East → EU-West: 30% packet loss, 800ms latency
- Normal: 100ms
- Health checks occasionally pass
  (monitoring says both regions are "healthy")
- EU user write latency: jumped from 50ms to 900ms

**Design task:**

1. Immediate mitigation:
   What do you do in the first 10 minutes?

2. Long-term fix:
   What architectural change prevents this from
   impacting users next time?

3. How do you detect a "gray failure" like this
   (not a full outage, but severe degradation)?

**Key tensions:**

- Health checks only detect binary up/down.
  A "gray failure" (slow but not dead) is much harder to detect.
- Mitigation may require rerouting EU writes to US primary,
  which creates a different latency problem
- The partial partition may resolve itself in minutes

**Hint to unlock after your attempt:**

- First 10 minutes:
  (1) Override EU-West to route writes to US-East primary directly.
      EU users get higher write latency (~150ms) but not 900ms.
  (2) Set a maintenance window and alert users if needed.
  (3) Engage network team and cloud provider support.
- Long-term fix: circuit breaker on the cross-region replication path.
  If cross-region RTT > 3× baseline for 30 seconds:
  automatically promote EU-West to accept writes locally.
  Accept temporary divergence. Reconcile after the partition heals.
- Gray failure detection:
  Use percentile-based health checks, not binary.
  Alert when P99 cross-region RTT > 300ms (3× baseline).
  Standard TCP health checks will not catch 30% packet loss.
  Use continuous synthetic probes with latency measurement.

---

**Question 8: Region Failure and Traffic Surge**

**Scenario:**

- US-East: 50% of traffic, EU-West: 30%, AP-Tokyo: 20%
- US-East fails. Geo-DNS reroutes US traffic.
- EU-West now receives 80% of global traffic
  (its normal 30% + rerouted US 50%)
- EU-West was sized for 30%

**Design task:**

1. What happens immediately when EU-West receives 2.7×
   its normal traffic volume?

2. Design the capacity management strategy
   to handle this scenario pre-planned.

3. Design a load shedding strategy for
   the moment EU-West is overwhelmed.

4. What SLO metrics do you publish
   for "degraded multi-region mode"?

**Key tensions:**

- Pre-scaling EU-West to absorb 80% of traffic at all times
  is extremely wasteful (costs 2.7× EU compute permanently)
- Auto-scaling takes 3–5 minutes, during which EU-West degrades
- Load shedding must be business-logic-aware
  (not all requests are equal)

**Hint to unlock after your attempt:**

- Capacity strategy:
  Run EU-West at 50% utilization normally (headroom for surge).
  This costs 1.67× more than tight-packed EU-West.
  Worth it for a critical SLA.
  Additionally: configure auto-scaling to trigger at 60% CPU.
  Warm instances in 3 minutes. Buy 2–3 minutes of breathing room.
- Load shedding tiers (in order of shedding priority):
  Tier 1: shed background jobs (analytics, reports) immediately
  Tier 2: shed non-authenticated read requests (rate limit aggressively)
  Tier 3: shed writes for non-critical features (profile updates, preferences)
  Never shed: financial transactions, authentication, core product writes
- Degraded SLO publication:
  Normal: 99.99% availability, P99 < 100ms
  Degraded: 99.5% availability, P99 < 500ms
  Publish the degraded SLO in your status page before incidents happen.
  Customers need to know what to expect.

---

**Question 9: Replication Lag and Security-Critical Writes**

**Scenario:**

- User changes password in US-East at 14:00:00 UTC
- At 14:00:01 UTC, an attacker (with old password)
  tries to log in from EU-West
- Replication lag: 3 seconds
- EU-West replica still has the old password

**Part 1 question:**

Does the attacker succeed?

What is the correct architecture to prevent this?

**Part 2 question:**

A user changes their profile picture.

Is async replication acceptable here?

Justify your answer.

**Key tensions:**

- Security-critical writes (password, MFA, session invalidation)
  must be consistent globally or they create exploits
- Profile picture changes have zero security impact
  and can tolerate eventual consistency
- Routing all reads to primary for security checks
  adds 75–100ms latency per login — is this acceptable?

**Hint to unlock after your attempt:**

- Part 1: Yes, the attacker succeeds. EU-West serves the login
  from its stale replica (old password is still valid there).
  3-second window is more than enough for an attack.
- Correct architecture: security-critical reads (login, MFA check,
  session validation) ALWAYS route to primary. No exceptions.
  The 75–100ms latency overhead per login is acceptable.
  Alternatively: after a password change, write a
  "security invalidation event" to a globally consistent store
  (e.g., DynamoDB global table or Redis Cluster with cross-region sync).
  Login checks this store first.
- Part 2: Yes, async replication is fine for profile pictures.
  Worst case: user sees their old profile picture for 3 seconds.
  Zero security or financial risk.
  This is the right use case for eventual consistency.

---

**Question 10: Configuration Drift Discovery**

**Scenario:**

- 3-region system, running for 6 months
- You discover Redis `maxmemory-policy` drift:
  - EU-West: `allkeys-lru` (correct)
  - US-East: `noeviction` (cache fills up → crashes under load)
  - AP-Tokyo: `volatile-lru` (only evicts keys with TTL set)
- None of this was intentional

**Design task:**

1. How did this drift happen?
   (What specific events cause configuration drift?)

2. What is the blast radius of `noeviction` in US-East
   under a cache memory pressure scenario?

3. Write the remediation steps. In what order?

4. Design the process that prevents drift in the future.

**Key tensions:**

- Fixing US-East Redis config is easy (one command)
  but doing it safely (without cache stampede) is not
- Preventing future drift requires tooling AND process changes
- Drift detection must be automated — humans reviewing
  configs monthly is not reliable enough

**Hint to unlock after your attempt:**

- How drift happens:
  An engineer SSH'd into US-East Redis at 2 AM during an incident
  and disabled eviction to stop the cache from dropping hot keys
  during the incident. They never reverted it.
  AP-Tokyo drift: a different team deployed a Redis config template
  that was never standardized across all regions.
- Blast radius of `noeviction`: at 100% memory usage,
  Redis returns OOM errors on every write.
  Your application's write-through cache breaks.
  Depending on error handling: either the request fails completely,
  or it falls back to DB (cache stampede at scale).
  Under 10K writes/second: your DB gets hammered.
  At 200K reads/second with cache miss: DB likely falls over.
- Remediation order:
  1. Take a snapshot of all three Redis configs NOW (for the incident record)
  2. Fix US-East first (highest blast radius: 50% of traffic)
  3. Use `CONFIG SET maxmemory-policy allkeys-lru` — online, no restart
  4. Fix AP-Tokyo
  5. Verify all three with `CONFIG GET maxmemory-policy`
- Prevention:
  Terraform for all Redis config (not just instance provisioning)
  `redis.conf` file in version control
  CI/CD drift check: run `terraform plan` daily, alert on non-empty plans
  Post-incident change reviews: any manual config change
  gets a Jira ticket and a PR to Terraform within 24 hours

---

### Theme C: Performance and Cost Optimization

---

**Question 11: Cross-Region Read Caching for ML Recommendations**

**Scenario:**

- `GET /user/recommendations` endpoint
- Reads 10 tables, calls 2 ML models, takes 2 seconds to compute
- EU users: 2 seconds compute + 100ms cross-region read = 2.1 seconds (barely ok)
- EU users pay 100ms cross-region penalty on EVERY other endpoint too

**Design task:**

Design a caching strategy for recommendations that:

1. Serves EU users locally (from EU-West cache)

2. Updates within 5 minutes of new data

3. Costs < $5K/month extra

4. Does not require a separate EU compute fleet
   to run the ML models

**Key tensions:**

- The cache must be pre-populated (not on first miss)
  because first-miss latency is 2.1 seconds
- Cache invalidation: when does a recommendation change?
  (New items, user behavior changes)
- The EU cache must be populated from the US-East ML result,
  not by running the ML model in EU again

**Hint to unlock after your attempt:**

- Architecture:
  US-East computes recommendations for all users (batched, every 5 minutes)
  Results stored in US-East Redis and immediately replicated to EU-West Redis
  EU-West serves recommendations from its local Redis (< 1ms)
  Cache key: `rec:user_id`. TTL: 10 minutes.
  On cache miss in EU-West: fall back to US-East API (2.1 seconds, acceptable)
- Population strategy:
  Batch job runs every 5 minutes in US-East
  Writes recommendation JSON to EU-West Redis via cross-region Redis pub/sub
  Ensures freshness within 5 minutes as required
- Cost estimate:
  50M users × 1KB recommendation payload = 50GB Redis per region
  ElastiCache r6g.2xlarge in EU-West: ~$500/month
  Cross-region replication of 50GB every 5 minutes is impractical
  Instead: only replicate for active users (5M daily active users × 1KB = 5GB)
  5GB × 12 times/hour × 24 hours × 30 days × $0.02/GB = ~$86/month
  Total: well under $5K/month

---

**Question 12: Cost-Justify a Third Region**

**Scenario:**

- Startup, $80K/month on multi-region (3 regions)
- Traffic: 85% US, 12% EU, 3% Asia
- AP-Tokyo: $20K/month compute + $10K DB = $30K/month
- CTO question: "Do we actually need AP-Tokyo for 3% of users?"

**Design task:**

1. Analyze what benefit AP-Tokyo provides for 3% of users.
   What is their experience without AP-Tokyo?

2. Build the cost justification math.
   At what revenue level is AP-Tokyo justified?

3. Design 3 options ranging from "decommission AP-Tokyo"
   to "keep but optimize."

4. What is the minimum viable multi-region setup
   for this traffic distribution?

**Key tensions:**

- 3% of users is small but AP users may be higher-value
  or have higher churn sensitivity to latency
- The $30K/month is 37.5% of total multi-region spend
  for 3% of traffic — clearly disproportionate
- Decommissioning is operationally complex:
  migration plan, user communication, DNS changes

**Hint to unlock after your attempt:**

- Without AP-Tokyo: AP users get ~150ms write latency (acceptable)
  and ~200ms API P99 (noticeable but not catastrophic).
  For a B2B SaaS: probably acceptable.
  For a consumer app (gaming, real-time): may cause churn.
- Cost justification math:
  If APJ revenue = $2M/year and AP-Tokyo reduces APJ churn by 0.5%:
  0.5% × $2M = $10K/year. AP-Tokyo costs $360K/year.
  Not justified at this scale.
  AP-Tokyo is justified when: APJ revenue > $72M/year
  (so that 0.5% churn reduction > $360K).
- 3 options:
  Option A: Decommission AP-Tokyo.
    AP users fall back to US-East. Savings: $30K/month.
    Migration: 2-week project.
  Option B: Convert AP-Tokyo to CDN-only (CloudFront + Redis).
    Cost: ~$3K/month (90% savings).
    Static assets and GET responses served locally.
    All write traffic goes to US-East.
  Option C: Keep AP-Tokyo but downsize.
    Scale down to 30% of current fleet (serve 3% of traffic).
    Move DB to read replica only (no failover capability).
    Savings: ~$18K/month.
- Minimum viable setup for this distribution:
  US-East (primary) + EU-West (full active-passive) + CDN globally.
  Total cost estimate: ~$50K/month vs current $80K.

---

**Question 13: Cross-Region Call Volume and Latency Cost**

**Scenario:**

- 1 million cross-region API calls per day
- AWS: $0.02/GB cross-region. Each call: 55KB.
- Monthly: 30M × 55KB = 1.65TB × $0.02 = $33/month
- But: each call adds 100ms to EU write latency
- At 10K EU writes/second, each requiring one cross-region call:
  10K concurrent requests × 100ms = capacity constraint

**Design task:**

1. Is $33/month the real cost of 1M calls/day?
   What are the hidden costs?

2. At what call volume does latency cost
   outweigh infrastructure cost?

3. Design 3 techniques to reduce cross-region calls.

4. For a write that requires cross-region validation
   (e.g., checking US-owned inventory from EU):
   can you batch or cache the validation?

**Hint to unlock after your attempt:**

- Hidden costs:
  The $33 data transfer is not the issue.
  The issue is: 100ms added to every EU write.
  At 10K writes/second: 10K threads × 100ms = throughput bottleneck.
  To serve 10K writes/second with 100ms cross-region call:
  you need 1,000 concurrent threads per region just for the cross-region calls.
  Thread pool exhaustion → queuing → latency cascade.
  The $33 data cost is irrelevant. The latency cost is the real problem.
- 3 techniques to reduce cross-region calls:
  (1) Cache cross-region validation results locally.
      If validating US inventory: cache the result for 5 seconds.
      Accept that 5-second staleness in exchange for eliminating the call.
  (2) Async validation: accept the write optimistically,
      validate cross-region asynchronously.
      If validation fails: compensate (refund, rollback).
      Works for eventually-consistent use cases.
  (3) Batch cross-region calls: instead of 1 call per request,
      accumulate 100 requests over 10ms, send 1 batched call.
      Reduces call count by 100×. Adds max 10ms batch wait.

---

**Question 14: Analytics Architecture — Three Options**

**Scenario:**

- Data team wants to query production data across 3 regions
- Option A: replicate all data to US-East data warehouse. Run analytics centrally.
- Option B: run analytics on regional read replicas. Federate results.
- Option C: run regional analytics jobs, aggregate summaries to US-East.
  Run global analytics on summaries.

**Design task:**

For each option, evaluate:

1. Query latency

2. Cost

3. Data freshness

4. GDPR compliance for EU data

5. Operational complexity

Then pick one and justify your choice.

**Hint to unlock after your attempt:**

Option A evaluation:
- Latency: fast (all data in one place)
- Cost: medium (one large warehouse + replication cost)
- Freshness: depends on replication frequency
- GDPR: VIOLATED if EU PII is copied to US warehouse
- Complexity: low (centralized)
- Verdict: disqualified by GDPR for most companies

Option B evaluation:
- Latency: slow for cross-region queries (federation overhead)
- Cost: medium (queries run on prod read replicas — resource contention)
- Freshness: very fresh (directly on replicas)
- GDPR: compliant (EU data never leaves EU)
- Complexity: high (federated query engine, join performance is painful)
- Verdict: acceptable but operationally painful

Option C evaluation:
- Latency: good (local summary computation, fast global aggregation)
- Cost: low (summaries are small: 99% compression vs raw data)
- Freshness: acceptable (hourly summaries, not real-time)
- GDPR: compliant (only anonymized summaries leave EU, never PII)
- Complexity: medium (one pipeline per region + central aggregation)
- Verdict: BEST option for most analytics use cases

Pick Option C. Justify: it satisfies GDPR, keeps costs low,
delivers daily/hourly analytics with acceptable freshness,
and doesn't impose load on production read replicas.

---

**Question 15: Global Full-Text Search Architecture**

**Scenario:**

- Global search service (full-text search across all user content)
- Option A: single Elasticsearch in US-East. All queries go to US-East.
  EU users: +100ms per search.
- Option B: Elasticsearch in all 3 regions, all documents replicated everywhere.
  Search locally.
- Option C: Elasticsearch per region with only that region's documents.
  Cross-region query federation for global search.

**Design task:**

For each option, evaluate:
latency, index size, replication cost, search consistency, complexity.

Design the architecture you would implement.

**Hint to unlock after your attempt:**

Option A:
- Latency: 100ms extra for EU/AP users
- Index size: 1× (single index)
- Replication: none
- Consistency: perfect
- Complexity: low
- Verdict: fine for a startup. Unacceptable at scale if EU is a major market.

Option B:
- Latency: < 10ms (local)
- Index size: 3× total storage
- Replication: high cost (all documents replicated 3×)
- Consistency: eventual (10-second lag between write and index)
- Complexity: medium (Elasticsearch cross-cluster replication)
- Verdict: works but expensive. 3× storage cost can be $50K+/month at scale.

Option C:
- Latency: < 10ms for regional queries,
  200–300ms for global cross-region federated queries
- Index size: 1× total (each region holds only its documents)
- Replication: minimal (only cross-region for global search)
- Consistency: good for regional queries
- Complexity: highest (federation layer, ranking across shards)
- Verdict: best for content that is naturally regional (EU content, US content).

Recommended: Option B for smaller datasets (< 1TB total).
Option C for large datasets where 3× storage cost is prohibitive.

---

### Theme D: Design from Scratch and Trade-offs

---

**Question 16: Global Session Store**

**Requirements:**

- 50M active users
- Session lookup: < 5ms globally
- Session invalidation propagates within 1 second globally
- 99.99% availability
- Sessions: 1KB each → 50GB total state

**Design task:**

1. How do you store 50GB of session state
   with < 5ms access in 3 regions?

2. What is the replication model for session invalidations?
   (Invalidations must reach all regions within 1 second)

3. What happens if the session store in one region goes down?

4. How do you handle session state during region failover?

**Hint to unlock after your attempt:**

- Storage: Redis in each region. 50GB fits in a single
  r6g.2xlarge (64GB RAM). Cost: ~$500/month per region.
  Read: local Redis, < 1ms. Total with network: < 5ms.
- Replication model:
  Active sessions: replicate asynchronously.
  Lag < 500ms is acceptable for normal session reads.
  Invalidations (logout, password change):
  use a pub/sub channel broadcast to all regions.
  Each region's Redis subscribes to the invalidation channel.
  On invalidation event: delete the key immediately.
  Target: < 1 second propagation (pub/sub is typically < 100ms).
- Invalidation path is separate from data path.
  Data replication: async, eventual.
  Invalidation: near-synchronous via pub/sub.
  This is the key architectural insight.
- Region failure: sessions in the failed region are unavailable.
  Users in that region must re-authenticate after failover.
  Acceptable for most applications.
  Alternative: replicate sessions to 2 regions (2× storage cost).
  Users don't see logout. Worth it for premium B2B products.

---

**Question 17: Globally Distributed Rate Limiter**

**Requirement:**

- Limit user_id to 1,000 API calls per minute globally
- 3 regions, each handling ~33% of requests
- A bot makes: 500/min to US, 400/min to EU, 300/min to Tokyo
  = 1,200/min total. Must be blocked.
- Per-region counting lets the bot through (each region sees < 1,000)

**Design task:**

Design a rate limiter that:

1. Enforces ~1,000 calls/minute with < 5% overdraft

2. Adds < 10ms latency per request

3. Handles regional failure gracefully

**Three options to evaluate:**

Option A: centralized counter in US-East

Option B: token bucket with periodic cross-region sync (every 10 seconds)

Option C: hash-based ownership (each user_id owned by one region)

**Hint to unlock after your attempt:**

Option A analysis:
- Latency: +75ms for EU, +150ms for Tokyo. Violates < 10ms requirement.
- Failure: if US-East rate limiter goes down: fail open (allow all) or fail closed (block all).
  Neither is acceptable without a secondary.
- Verdict: eliminated by latency requirement.

Option B analysis:
- Each region has a local counter. Sync every 10 seconds.
- Worst-case overdraft: a user makes 1,000 calls to each region
  between syncs = 3,000 calls in 10 seconds.
  Real overdraft = (sync_interval / 60_seconds) × limit × num_regions.
  At 10s sync: (10/60) × 1,000 × 3 = 500 overdraft calls.
  50% overdraft — too high for a payment API.
  Reduce sync interval to 2 seconds: overdraft drops to ~100 (10%).
  Still above 5% threshold.

Option C analysis:
- user_id → hash → owning region. Deterministic.
- All rate limit checks for user_id 12345 go to US-East
  (regardless of which region received the request).
- Non-owning regions (EU, Tokyo): make one cross-region call per request.
  Latency: +75–150ms for non-owning regions.
  Better than Option A because only rate limit calls are remote,
  not the full request processing.
- If owning region fails: fail open temporarily.
  On recovery: replay the missed counter increments.

Recommendation:
- Payment API: Option C. Accurate, deterministic.
  Accept the cross-region hop for non-owning regions.
- Search/content API: Option B with 2-second sync.
  10% overdraft acceptable. Low latency more important.

Redis sliding window implementation:

```
Key: rate:user:12345
ZADD rate:user:12345 <now_ms> <request_uuid>
ZREMRANGEBYSCORE rate:user:12345 0 <(now_ms - 60000)>
count = ZCARD rate:user:12345
if count > 1000: reject
```

---

**Question 18: Content Moderation Propagation**

**Scenario:**

- Global social network
- 50K posts/day flagged for policy violations
- Must be hidden globally within 30 seconds of being flagged
- Normal post replication lag: 2–5 seconds
- But you need < 30 seconds GUARANTEED for moderation actions

**Design task:**

1. Why is normal post replication insufficient for moderation?

2. Design the moderation propagation system.

3. Why should moderation updates use a different
   replication path than normal posts?

4. What happens if the moderation event fails to reach
   one region? (Eventual consistency vs guaranteed delivery)

**Hint to unlock after your attempt:**

- Why normal replication is insufficient:
  2–5 seconds is the AVERAGE. P99 lag can be 30–60 seconds.
  Under network congestion: minutes.
  You need a GUARANTEED upper bound, not an average.
  Normal post replication shares bandwidth with millions of other events.
  Moderation events must jump the queue.
- Architecture:
  Separate replication path for moderation events:
  Moderation service → dedicated high-priority Kafka topic
  → regional consumers (one per region)
  → regional content visibility store (Redis or DynamoDB)
  Regional content visibility store: key = post_id, value = visible/hidden
  Every content request checks this store first (before fetching content)
  Redis read: < 1ms. Adds no meaningful latency to content requests.
- Guaranteed delivery:
  Use Kafka with acks=all (replication factor 3 for the moderation topic)
  Regional consumer: commit offset only after writing to visibility store
  End-to-end: moderation event → Kafka → regional Redis → visible to check
  Target: < 5 seconds for the happy path. < 30 seconds for P99.
- If a region misses a moderation event:
  Dead letter queue + retry with exponential backoff.
  Fallback: hourly full reconciliation of moderation table
  across all regions (catch any missed events).

---

**Question 19: Zero-Downtime Multi-Region DB Migration**

**Scenario:**

- PostgreSQL primary: us-east-1, 10 read replicas in us-east-1 only
- Target: read replicas in eu-west-1 and ap-northeast-1 too
- Load: 200K reads/second, 5K writes/second
- Zero-downtime requirement during migration

**Design task:**

1. How do you add the first EU replica without downtime?

2. How do you route EU traffic to it
   without a hard cutover?

3. What can go wrong? (Name 3 failure modes)

4. How do you roll back if the EU replica
   starts serving stale data to users?

**Hint to unlock after your attempt:**

- Adding the first EU replica:
  Provision a new RDS instance in eu-west-1
  Set up streaming replication from us-east-1 primary
  (Postgres physical replication or logical replication via pglogical)
  Initial sync: snapshot + WAL replay. Takes hours for large databases.
  During sync: EU replica is in "catching up" state.
  Do NOT route traffic to it yet.
  When replica lag < 100ms: mark it as ready.
  Zero downtime: the primary never stops. Read replicas are additive.
- Traffic routing:
  Use weighted routing in your load balancer or service mesh.
  Start at 0% EU traffic → EU replica.
  Ramp: 1%, 5%, 10%, 25%, 50%, 100% over 2 weeks.
  At each step: monitor read latency and replica lag.
  If either degrades: pause the ramp, investigate.
  Canary: route only internal traffic (your own employees) first.
- Failure modes:
  (1) Network partition between us-east-1 and eu-west-1:
      replica falls behind. Traffic must fail back to primary.
  (2) Schema migration applied to primary but not yet replicated:
      EU replica serves old schema for a few seconds.
      Application must handle both schema versions.
  (3) Connection pool exhaustion on EU replica:
      too many connections from the region routing.
      Need a connection pooler (PgBouncer) per region.
- Rollback: set EU region traffic weight back to 0% immediately.
  The routing change takes < 30 seconds.
  No data loss: EU replica was read-only.

---

**Question 20: Global Configuration Store**

**Requirements:**

- Used by 500+ microservices across 3 regions
- Reads: < 2ms (config is on the hot path)
- Config updates: propagate to all regions within 5 seconds
- Updates are infrequent: 1–2 per day per service

**Design task:**

1. Design the storage layer and replication model.

2. Design the client-side caching layer.
   What TTL? What happens on cache miss?

3. What happens if a config value differs between
   US-East and EU-West for 3 seconds?
   Is this acceptable?

4. How do you handle a bad config push
   (a config value that breaks a service)?

**Hint to unlock after your attempt:**

- Storage layer:
  Each region runs a local config service (e.g., Consul or etcd or a simple Redis).
  Config is written to a global primary (one region owns writes).
  Writes replicate to all regions via Kafka (durable, ordered).
  Regional config service consumes the Kafka topic and applies updates locally.
  Replication latency: < 2 seconds (Kafka + consumer processing).
  Well within the 5-second requirement.
- Client-side caching:
  Each microservice caches config in memory (local process cache).
  TTL: 30 seconds. On TTL expiry: refetch from local regional config service.
  Config service read latency: < 1ms (in-memory Redis or etcd).
  Total client read latency: 0ms (from process cache) or < 1ms (from regional service).
  Satisfies the < 2ms requirement.
- 3-second inconsistency:
  Acceptable in most cases. Config updates happen 1–2 times per day.
  A 3-second window where US-East has new config and EU-West has old:
  If the config change is additive (new feature flag): EU-West serves
  the old behavior for 3 seconds. Invisible to users.
  If the config change is breaking (DB hostname change): you have a problem.
  Mitigation: for critical config changes, use a 2-phase rollout:
  Phase 1: push config to all regions and wait for propagation confirmation.
  Phase 2: activate the config change only after all regions acknowledge.
- Bad config push:
  Every config write goes through a config validation step (schema check).
  After propagation: each regional service runs a canary check on the new config.
  If canary fails: auto-rollback (set config back to previous version).
  The previous version is always stored (1 version of history minimum).
  Rollback propagation: same path as forward push (< 5 seconds).

---

## 3. Homework Exercises

6 exercises. Work through them before reading the hints.

---

### Exercise 1: Active-Passive Failover Design

Time: 25 minutes

**Setup:**

- E-commerce company. 1 region today: us-east-1.
- 100% of traffic.
- Business requirement: survive a full us-east-1 outage.
  RTO < 5 minutes, RPO < 30 seconds.
- Primary database: PostgreSQL.
- Application: 10 stateless API servers behind an ALB.
- Current state: no disaster recovery plan exists.

**Your tasks:**

1. Design the full active-passive architecture
   with eu-west-1 as the standby region.

   Which services need a standby instance?

   Which can be cold-started on demand during failover?

2. Choose sync or async replication for the database.

   Justify your choice against the RPO requirement.

3. Write the 8-step failover runbook in order.

   Your runbook must include:
   - The health check threshold that triggers failover
   - The STONITH step
   - The DNS update step
   - A verification step at the end

4. How do you test this failover without touching production?

5. US-East recovers after a successful failover to EU-West.

   How do you fail back?

   What data reconciliation is needed before switching writes back?

---

**L6 Answer Key**

Task 1 — What needs standby vs cold-start:

Needs standby (must be running before failover):
- PostgreSQL replica (takes hours to build from scratch)
- Redis replica (cache warmup takes time, cold cache = DB overload)
- Geo-DNS configuration (must be pre-configured, not created during failover)

Can cold-start in < 3 minutes (fine for 5-min RTO):
- EC2 API servers (stateless, AMI-backed, auto-scaling group launches in 90 seconds)
- ALB (provisions in 2 minutes)
- Application config (from Parameter Store, available in eu-west-1)

Task 2 — Replication choice:

Choose: async replication.

Justification:
- RPO = 30 seconds. Async replication lag = 1–5 seconds normally.
  30 seconds is achievable with async.
- Sync replication adds 75ms to every US-East write (US → EU RTT).
  At 5K writes/second: unacceptable write latency increase.
- Semi-sync: one sync replica (adds 75ms). Not needed here.
  RPO 30 seconds is achievable with async.
- Monitor replication lag: alert at > 10 seconds.
  If lag > 30 seconds: automatically pause writes (fail-fast before RPO violated).

Task 3 — 8-step failover runbook:

Step 1: Confirm failure (not a false alarm).
  Require 3 consecutive failed health checks over 60 seconds
  from at least 2 independent monitoring locations.

Step 2: Page the on-call engineer.
  Do not proceed with automated failover without human acknowledgment
  (for a first implementation).

Step 3: STONITH — fence the us-east-1 primary.
  Action: use AWS API to force-stop the RDS instance.
  Or: revoke the db security group rule to reject all connections.
  This ensures us-east-1 cannot accept any more writes.

Step 4: Verify replication position.
  Note the last applied LSN on eu-west-1 replica.
  Confirm no further replication lag is growing (it should stop growing
  since us-east-1 is now fenced).

Step 5: Promote eu-west-1 replica to primary.
  Command: `aws rds promote-read-replica --db-instance-identifier eu-west-prod-replica`
  Wait for promotion to complete (typically 30 seconds).

Step 6: Update application config.
  Update the DB_HOST parameter in AWS Parameter Store eu-west-1
  to point to the newly promoted primary.
  Restart or trigger a config reload on eu-west-1 API servers.

Step 7: Update DNS.
  Change the api.yourcompany.com DNS record to point to eu-west-1 ALB.
  Use Route53 health check-based routing or manual update.
  TTL must already be set to 60 seconds (pre-configured before this event).
  Wait 60 seconds for DNS propagation.

Step 8: Verify.
  Run a synthetic transaction end-to-end: place a test order, confirm it writes.
  Check application error rates. Confirm < 1% error rate.
  Check DB write latency. Confirm < 50ms.
  Declare failover complete. Log the time.

Task 4 — Testing without production impact:

Option A: Shadow failover test.
  During a low-traffic maintenance window (2 AM Sunday):
  Set eu-west-1 replica to accept test writes for 5 minutes
  while us-east-1 primary continues.
  Does NOT test real DNS failover but tests DB promotion.

Option B: Chaos engineering test.
  Use a "dark launch" test in us-east-1:
  Simulate a failover by temporarily routing 0.1% of traffic
  through the eu-west-1 path (but not promoting the DB).
  Verify end-to-end latency and error rates.

Option C: Full tabletop test.
  Run the entire runbook against a staging environment
  that mirrors production (same instance sizes, same replication config).
  This is the most comprehensive test.

Recommendation: do Option C quarterly. Do Option A monthly.

Task 5 — Failback to us-east-1:

Step 1: Do NOT rush failback.
  Every minute of continued operation in eu-west-1 adds more data
  that must eventually sync back. Stabilize first.

Step 2: Set up us-east-1 as a replica of eu-west-1.
  Once us-east-1 comes back online: configure it as a read replica
  of the eu-west-1 primary.
  Let it catch up (fully replicate all writes made during the outage).

Step 3: Wait for us-east-1 replica lag = 0.

Step 4: Maintenance window.
  Schedule a 2-minute maintenance window.
  During this window: no new writes accepted.

Step 5: Promote us-east-1 back to primary.
  Follow the same runbook steps (STONITH eu-west-1, promote us-east-1, update DNS).

Step 6: Data reconciliation.
  For any writes made to eu-west-1 after the replication cutoff
  (i.e., any writes after us-east-1 came back online as replica):
  these are already replicated. No reconciliation needed.
  The replica lag tracking ensures this.

---

### Exercise 2: Conflict Resolution Design

Time: 25 minutes

**Setup:**

- Note-taking app (like Notion).
- Active-active: US users write to US-East, EU users write to EU-West.
- A user edits the same note on their laptop (US-East)
  and phone (EU-West) simultaneously.

**Your tasks:**

1. Describe what happens with Last-Write-Wins (LWW).

   Give a concrete example with timestamps and content.

   What data is lost?

2. Design a vector clock approach for this app.

   What does the client store?

   What does the server store?

   How is a conflict detected?

   What does the user see when a conflict occurs?

3. For each data type in a note
   (title, text body, tags, last-modified timestamp):

   Is LWW safe? Or does it require vector clocks?

   Justify for each.

4. For the text body specifically:

   Could you use a CRDT?

   Which CRDT would work for text editing?

   Name it. Explain how it handles concurrent inserts.

5. This app has 5M active users.

   0.1% experience conflicts per day = 5,000 conflicts/day.

   At this scale: user-visible conflict resolution
   or automatic resolution?

   What is the UX for each?

---

**L6 Answer Key**

Task 1 — LWW concrete example:

Note content at 14:00:00 UTC (both devices start with same version):
"Meeting agenda: discuss Q3 roadmap"

Laptop (US-East), 14:00:05 UTC:
User adds: "Meeting agenda: discuss Q3 roadmap\n1. Budget review"
Write sent to US-East. Timestamp: 14:00:05.

Phone (EU-West), 14:00:06 UTC (1 second later):
User adds: "Meeting agenda: discuss Q3 roadmap\n2. Hiring plan"
Write sent to EU-West. Timestamp: 14:00:06.

LWW result after async replication sync:
EU-West write wins (later timestamp).
Final note: "Meeting agenda: discuss Q3 roadmap\n2. Hiring plan"
The laptop's "1. Budget review" is silently lost.

This is a real data loss. The user will be confused and frustrated.
LWW is never acceptable for collaborative text editing.

Task 2 — Vector clock design:

Client stores:
- note_id: string
- vector_clock: map of {server_id → sequence_number}
  Example: {"us-east": 5, "eu-west": 3}
- content: the full note text

Server stores:
- note_id → (content, vector_clock)
- Conflict log: when a conflict is detected, both versions stored

Conflict detection:
When EU-West receives a write with vector clock VC_client:
Compare VC_client to VC_server (current server version).
If VC_client > VC_server on all dimensions: no conflict. Normal write.
If VC_client < VC_server on some dimensions AND > on others:
  → CONCURRENT writes detected → CONFLICT.
  Both versions are stored. User is notified.

User sees: "Conflict detected. Two versions of this note exist.
  Version A (laptop): [content]
  Version B (phone): [content]
  Merge or choose one."

Task 3 — Data type analysis:

Title:
- LWW: acceptable. Rarely edited simultaneously.
  Risk of silent loss is low. User can easily retype a title.
  Accept LWW for simplicity.

Text body:
- LWW: NOT acceptable. See the example above.
  Requires OT (Operational Transformation) or CRDT.

Tags (a set of strings like ["work", "Q3", "budget"]):
- LWW: NOT acceptable. One device adds "work", other adds "Q3".
  LWW loses one.
- But a Set CRDT (OR-Set / Observed-Remove Set) is perfect here.
  Both "work" and "Q3" survive. No conflict. No user intervention.

Last-modified timestamp:
- LWW: acceptable and correct. The later timestamp is the right one.
  This is a metadata field, not user content.

Task 4 — CRDT for text:

CRDT: RGA (Replicated Growable Array) or YATA

How RGA handles concurrent inserts:

Every character in the document gets a unique ID (node_id).
An insert operation is: "insert character 'x' after node_id:42"
When two users insert at the same position simultaneously:
Both insert operations arrive at each replica.
RGA uses a deterministic tie-breaking rule (e.g., by user_id)
to decide the order of concurrent inserts at the same position.
The result: both characters are preserved, with a consistent
ordering that every replica agrees on.

This is used in production by: Yjs (used by Notion, Figma),
Automerge, and ShareDB.

Task 5 — Scale analysis:

5,000 conflicts/day with user-visible resolution:
If each conflict requires the user to manually merge:
5,000 support tickets/day → unmanageable.
User churn: 5,000 users/day seeing their data conflict = bad NPS.

5,000 conflicts/day with automatic resolution (OT/CRDT):
Most conflicts are resolved silently.
Users see a merged result that preserves both edits.
The experience is: your edit is always preserved.
This is how Google Docs works. Users love it.

Verdict: at any meaningful scale, automatic resolution is required.
User-visible conflict resolution is acceptable only during the MVP phase
when you have < 100 active users and can explain to them manually.

---

### Exercise 3: Replication Lag Impact Analysis

Time: 20 minutes

**Setup:**

- Online banking app.
- Active-passive: US-East primary, EU-West read replica.
- Replication lag: 2–4 seconds async.
- Three operations:
  1. User transfers $500 to a friend (write → US primary)
  2. User checks balance immediately after (read → EU replica)
  3. User's friend checks if they received $500 (read → EU replica)

**Your tasks:**

1. For operation 2: what does the user see?

   Is this a problem? What is the specific risk?

2. For operation 3: what does the friend see?

   Is this more or less serious than operation 2?

3. Design a read-after-write consistency solution for operation 2.

   What token do you pass?

   How does the replica honor it?

   What is the latency impact?

4. For balance checks in a banking app:

   Should you use async replication at all?

   Design the read path for "show my balance"
   that guarantees no stale reads.

5. Replication lag suddenly grows to 45 seconds.

   What alert fires?

   What automatic action happens?

   What do you tell users who call support?

---

**L6 Answer Key**

Task 1 — User sees stale balance:

User transferred $500 at 14:00:00.
User checks balance at 14:00:02 (2 seconds later).
EU-West replica has lag of 3 seconds.
Replica still shows the old balance ($500 still in account).
User sees: "Balance: $1,000" (as if the transfer didn't happen).

The specific risk: the user believes the transfer failed.
They initiate a second transfer of $500.
If the application doesn't have idempotency protection:
the second transfer executes → user sends $1,000 total.
This is a real financial risk.

Task 2 — Friend's perspective:

Friend checks balance at 14:00:03 (3 seconds after transfer).
EU-West replica still stale.
Friend sees: "Balance: $2,000" (before the $500 arrived).

Is this more or less serious?
It depends on the relationship:
- If the friend is waiting to confirm payment before sending goods:
  same risk as operation 2 — they may think payment didn't arrive
  and not release the goods.
- In isolation: it's slightly less serious because the friend
  is reading their own balance, not triggering a retry of the write.
  The user (who made the write) is more likely to retry.

Task 3 — Read-after-write solution:

After a write, return the PostgreSQL LSN (Log Sequence Number)
in the response header: `X-Write-Checkpoint: 00000005/3A000028`

The client (browser or mobile app) stores this value in a cookie:
`read_checkpoint=00000005/3A000028; max-age=30`

On the next read request, the client sends the cookie.

The API server checks the EU-West replica's current applied LSN:
`SELECT pg_last_wal_replay_lsn();`

If replica LSN >= checkpoint LSN: serve from replica. (Fast path)
If replica LSN < checkpoint LSN: route request to US-East primary. (Fallback)

The cookie expires after 30 seconds. After 30 seconds:
replication lag should have cleared. Resume serving from replica.

Latency impact:
- Happy path (replica has caught up): 0ms overhead.
  Just a replica read.
- Slow path (replica behind): redirect to primary adds 75ms.
  Only affects requests within 30 seconds of a write.
  For a transfer: the user makes 1 write and then 1–2 reads.
  The fallback to primary happens for those 1–2 reads only.
  Acceptable overhead.

Task 4 — Banking balance read path:

For a banking app: always read balance from primary.

No stale reads, ever.

Implementation:
Tag the balance endpoint: `read-consistency: strong`
API gateway routing: any request with this tag goes to primary.
All other endpoints: can use replica.

This is called read-your-writes + monotonic read consistency.
For financial balances: the extra 75ms is worth it.
Users are already waiting for a bank page to load.
75ms is imperceptible.

Task 5 — Lag grows to 45 seconds:

Alert fires at > 30 seconds lag:
Alerting rule: `replica_lag_seconds{region="eu-west"} > 30`
PagerDuty page to on-call engineer.

Automatic action at 30+ second lag:
Load balancer routing rule update:
All reads (not just balance) that normally go to EU-West replica
are temporarily redirected to US-East primary.
This is a traffic shift, not a failover. The replica is still up.
The primary absorbs additional read traffic.
Monitor primary CPU. If > 80%: shed non-critical reads.

Support communication:
"We are currently experiencing a brief delay in balance display
for some European users. Your transactions are being processed
normally. Please allow a few minutes for balances to update."

Do NOT say: "replication lag." Say: "brief display delay."

When lag recovers to < 5 seconds: automatically switch reads back to replica.

---

### Exercise 4: Multi-Region Cost Audit

Time: 20 minutes

**Setup:**

- 3-region system: US-East (primary), EU-West, AP-Tokyo
- Monthly AWS bill: $120K
  - Compute (EC2): $60K (20 servers × 3 regions, $1K/server)
  - Database (RDS): $30K (3 regions × $10K each)
  - Data transfer (cross-region): $18K
  - Load balancers + misc: $12K
- Traffic: US-East 55%, EU-West 35%, AP-Tokyo 10%

**Your tasks:**

1. AP-Tokyo: 10% of traffic, 33% of compute cost ($20K/month).

   At what revenue level is AP-Tokyo justified?
   (Assume it reduces APJ churn by 0.5%, increasing APJ revenue by 0.5%)

2. Identify 3 cost reduction opportunities.

   For each: estimated savings, risk, implementation time.

3. Data transfer: $18K/month.

   What data is being replicated?

   Can any be compressed more, filtered, or batched?

   Design a 30% reduction in replication data transfer.

4. Design a "minimum viable multi-region" that:
   - Keeps EU-West as full active-passive
   - Converts AP-Tokyo to edge cache only (CDN + Redis, no compute)

   Estimate the new monthly cost.

---

**L6 Answer Key**

Task 1 — AP-Tokyo cost justification:

Math:
AP-Tokyo cost: $20K compute + $10K DB = $30K/month = $360K/year.

Assume APJ (Asia-Pacific-Japan) users represent X% of annual revenue.
AP-Tokyo adds 0.5% improvement in APJ revenue
(reduced churn from lower latency).

For AP-Tokyo to break even: 0.5% × APJ_revenue = $360K/year
→ APJ_revenue must be ≥ $72M/year.

If total company ARR is $50M and APJ is 10% of that:
APJ_revenue = $5M/year. 0.5% = $25K. Far below $360K.

At this revenue level: AP-Tokyo is not financially justified.

However: if AP-Tokyo is a strategic market (e.g., a large enterprise deal
requires data residency in Japan), the financial math is secondary.
Non-financial justifications must be explicit and documented.

Task 2 — 3 cost reduction opportunities:

Opportunity A: Spot instances for AP-Tokyo compute.

AP-Tokyo is a read-only replica region.
If the spot instance is interrupted: AP-Tokyo traffic falls back to US-East.
Users see +150ms latency for a few minutes.

For the AP-Tokyo compute fleet (not the DB):
Migrate EC2 to spot instances.
Savings: 60–70% on compute.
$20K × 65% = $13K/month savings.
Risk: low (stateless compute, graceful fallback exists).
Implementation time: 1 week.

Opportunity B: Reserved instances for US-East and EU-West DBs.

Current: on-demand RDS pricing.
1-year reserved instance: ~35% savings.
$10K × 2 regions × 35% = $7K/month savings.
Risk: none (it's a billing commitment, not an architecture change).
Implementation time: 1 day.

Opportunity C: Compress cross-region replication traffic.

See Task 3 below. ~$5.4K/month savings (30% of $18K).
Risk: low (compression is a config change in most replication tools).
Implementation time: 2–3 days.

Total potential savings: $13K + $7K + $5.4K = $25.4K/month.
New bill: $94.6K/month (down from $120K, -21%).

Task 3 — Reduce replication data transfer by 30%:

Current: $18K/month for 1.65TB/month cross-region replication.
That is ~55GB/day.

What is being replicated?
- Database WAL/binlog changes: ~20GB/day
- Application-level event replication (Kafka → regional consumers): ~15GB/day
- Blob/binary data (images, attachments replicated to all regions): ~20GB/day

Where to cut:

Binary data (images, attachments):
These should be in S3 with cross-region replication.
S3 CRR (Cross-Region Replication) uses native AWS compression.
Additionally: don't replicate full objects to AP-Tokyo
if AP-Tokyo doesn't serve reads of those objects.
Filter: only replicate to the region that actually serves the data.
Estimated savings: 40% of binary data = ~8GB/day = ~$5/day = $150/month.

Kafka event stream:
Enable Snappy or LZ4 compression on the Kafka replication topics.
Most JSON event payloads compress at 70–80% ratio.
15GB/day × 75% compression = 11.25GB/day savings.
= ~$6.75/day savings = $200/month.

Database WAL:
Postgres WAL compression (`wal_compression = lz4` in postgresql.conf).
Typical WAL compression ratio: 40–60%.
20GB/day × 50% = 10GB/day saved = ~$6/day = $180/month.

Total estimated savings: ~$530/month on data transfer.
That's $530 / $18,000 = ~3% — less than 30%.

Better path to 30% savings:
Stop replicating bulk analytics data cross-region entirely.
If the data team is replicating full event tables to US-East for analytics:
replace with Summary Only approach (as in Question 14).
This can cut the analytics portion of cross-region traffic by 90%.
If analytics data is 35% of the $18K ($6.3K):
cutting it by 90% saves $5.67K/month.
Combined with compression: total savings = $6.2K/month (34%).
Exceeds the 30% target.

Task 4 — Minimum viable multi-region with AP-Tokyo as edge:

New architecture:

US-East (primary):
- All writes land here
- RDS primary (unchanged)
- 20 EC2 API servers (unchanged)
- Cost: $40K/month (unchanged)

EU-West (full active-passive):
- RDS read replica (unchanged)
- 20 EC2 API servers (unchanged)
- Promotes to primary if US-East fails
- Cost: $40K/month (unchanged)

AP-Tokyo (edge cache only):
- CloudFront CDN: caches static assets and cacheable API responses
- ElastiCache Redis (2 nodes, r6g.large): caches session data and hot reads
- No EC2 compute fleet. No RDS instance.
- All writes go to US-East via the internet (+150ms)
- Cacheable reads served locally by Redis + CloudFront (< 10ms)
- Cost estimate:
  CloudFront: ~$500/month for 10% of traffic
  ElastiCache Redis (2x r6g.large): ~$800/month
  Data transfer (US-East → AP-Tokyo for cache population): ~$200/month
  Total AP-Tokyo: ~$1,500/month

New total monthly cost:
US-East: $40K
EU-West: $40K
AP-Tokyo: $1.5K
Data transfer and misc (reduced): ~$14K
Total: ~$95.5K/month

Previous: $120K/month.
Savings: ~$24.5K/month (~20%).
AP-Tokyo alone drops from $30K to $1.5K (-95%).

---

### Exercise 5: Incident Response — Split-Brain

Time: 30 minutes

**Setup:**

- You are on-call. 3:15 AM.
- Alert: "EU-West database promoted to primary.
  US-East database is also accepting writes. SPLIT BRAIN DETECTED."
- Current state:
  - US-East DB: 2,847 writes in the last 8 minutes
  - EU-West DB: 1,203 writes in the last 8 minutes
  - Both believe they are primary
  - Cause: 43-second network maintenance window triggered automated failover

**Your tasks:**

1. First 5 minutes:

   What are the top 3 actions you take immediately?
   (Before you understand the full scope)

2. How do you stop new writes from making things worse?

   You cannot take the product fully offline (payment processor).

3. Walk through the exact reconciliation steps for 4,051 diverged writes.

   How do you determine the "correct" version of each conflicting record?

4. For payment records:

   What additional information do you need to reconcile correctly?

5. Post-incident: design 3 changes that would have prevented this.

   For each: what specific step in the 43-second event sequence
   would it have changed?

---

**L6 Answer Key**

Task 1 — First 5 minutes:

Action 1: Fence one database immediately.

Do not try to understand everything first.
Stopping the bleeding is more important than diagnosis.
Decision: which DB to fence?
Default: fence the one that was promoted via automated failover
(EU-West) since it was the secondary.
US-East is the historical primary — it likely has more correct data.
Execute: `aws rds modify-db-instance --db-instance-identifier eu-west-prod --no-multi-az`
Or: revoke the eu-west DB security group inbound rule.
EU-West DB is now read-only. No new writes accepted.

Action 2: Page a second engineer immediately.

Split-brain reconciliation requires two people.
One to operate, one to review decisions.
Never reconcile a payment DB alone at 3 AM.

Action 3: Notify the incident commander and start an incident channel.

Open a Slack incident channel. Post the current state.
This is not paperwork. This is how you coordinate the next 3–4 hours.
Everyone who will be involved needs real-time updates.

Task 2 — Stop writes without full downtime:

DO NOT take the payment processor fully offline.

Instead: route all new incoming payments to US-East DB only.
Update the application-level router config:
database.primary_host = us-east-prod.rds.amazonaws.com
database.readonly_host = us-east-prod.rds.amazonaws.com

EU-West DB: already fenced (read-only). Accepts no new writes.
EU-West application servers: still serve read traffic.
Their write requests route to US-East (accepting the +75ms latency cost).

This is a degraded mode, not an outage.
Users can still make payments. EU writes are slower but functional.

Task 3 — Reconciliation steps:

Step 1: Pull the WAL from both DBs.

Extract binlog/WAL from both US-East and EU-West
from the divergence point onward.
Divergence point: the last common transaction before the split.
Find it by comparing transaction IDs / GTIDs.

Step 2: Categorize every write from EU-West (the loser's log).

For each of the 1,203 EU-West writes:
Category A: unique write (no corresponding US-East write on the same row).
  Action: apply to US-East. No conflict. Straightforward.
Category B: same row_id updated in both DBs (conflict).
  Action: requires business-logic resolution. See Task 4.
Category C: deleted in EU-West, not deleted in US-East.
  Action: review case by case. Deletion is usually safer to keep (not apply).

Step 3: Apply Category A writes to US-East.

Use the DB's point-in-time restore tooling or direct SQL.
DO this in a transaction. Do NOT commit until all Category A writes are verified.

Step 4: Resolve Category B conflicts manually.

For each conflicting row: pull the value from US-East and EU-West.
Present both to a second engineer for review.
Business logic drives the decision (see Task 4 for payments).

Step 5: After all writes reconciled: verify row counts match expected state.

Run a checksum comparison of critical tables between the reconciled DB
and the application's expected state (if available from event logs).

Step 6: Remove the EU-West fence. Allow EU-West to re-sync as a replica.

Total time: 2–6 hours depending on conflict count.

Task 4 — Payment record reconciliation:

The payment processor (Stripe, Adyen, etc.) is the authoritative source.

For every conflicting payment row:

Question 1: Did the payment processor charge the customer?
  Check the processor API: `GET /charges/{charge_id}`
  If the processor shows one successful charge: that's the truth.
  One of the two DB rows is a duplicate. The other is correct.

Question 2: Is there an idempotency key on the write?
  Well-designed payment systems attach an idempotency key to each write.
  If US-East and EU-West both have a row with the same idempotency key:
  they represent the SAME payment attempt, not two different payments.
  Keep the row from the DB that has the processor's confirmation ID.
  Discard the other.

Question 3: Did the processor show two charges?
  This is rare but possible (idempotency key was not used).
  Action: refund the duplicate charge immediately.
  Then reconcile the DB to show one charge.

Task 5 — Three prevention changes:

Change 1: STONITH before promotion.

What would have changed:
When the 43-second network maintenance window began,
the automated failover detected US-East as "unreachable."
Without STONITH: failover promoted EU-West while US-East was
still alive (just partitioned). Both became primary.
With STONITH: before promoting EU-West, the system would have
stopped the US-East RDS instance via the AWS API.
US-East would have been verifiably dead before EU-West promoted.
Split-brain impossible.

Change 2: Higher health check threshold before triggering failover.

What would have changed:
The failover triggered after a brief 43-second connectivity loss.
Network maintenance windows are a common cause of false positives.
With a higher threshold: require 5 consecutive failures over 90 seconds
(not 1–2 failures over 43 seconds) before triggering automated failover.
The 43-second blip would not have met the threshold.
No failover triggered. No split-brain.

Change 3: Automatic re-join as replica (not primary) on reconnection.

What would have changed:
When US-East came back online after the 43-second blip:
it resumed as primary (it still believed it was primary).
With the prevention change: any DB instance that goes offline and
comes back online MUST start in a read-only/replica mode
and explicitly wait for a re-promotion signal.
It should never self-promote or self-resume as primary.
This prevents the "zombie primary" problem that causes split-brain.

---

### Exercise 6: Design a Global Rate Limiter

Time: 25 minutes

**Setup:**

- API allows 1,000 requests per minute per user_id (globally enforced)
- 3 regions: US-East, EU-West, AP-Tokyo (~33% each)
- A bot: 500/min to US, 400/min to EU, 300/min to Tokyo = 1,200/min total
- Per-region counting: each region sees < 1,000 → bot bypasses the limit

**Your tasks:**

1. Design Option A: centralized counter in US-East.

   What latency does this add per request in each region?

   What is the failure mode if the central counter goes down?

2. Design Option B: token bucket with 10-second cross-region sync.

   How much overdraft can occur in the worst case?

   Is this acceptable?

3. Design Option C: hash-based ownership.

   Each user_id is owned by one region (by hash).

   What is the latency overhead for non-owning regions?

   What happens if the owning region fails?

4. Pick one option for:

   (a) A payment API (accuracy is critical)

   (b) A search API (approximate is acceptable)

   Justify both choices.

5. Sketch the Redis data structure for a sliding window rate limiter
   using sorted sets.

   What commands do you use?

   What is the time complexity?

---

**L6 Answer Key**

Task 1 — Option A: Centralized counter:

Architecture:
All 3 regions, for every incoming request, make a call to
a rate limit service running in US-East.
The US-East Redis stores the counter:
`INCR rate:user:12345` and `TTL` managed per minute.

Latency impact:
- US-East → own region: < 1ms. Acceptable.
- EU-West → US-East rate limit call: +75ms per request. Problematic.
- AP-Tokyo → US-East: +150ms per request.
  At 1,000 requests/second for AP-Tokyo: 1,000 × 150ms = crushing overhead.

Violates the < 10ms latency requirement for EU and AP regions.

Failure mode:
If US-East rate limit service goes down:
Option A (fail open): all requests allowed. Bot gets through.
Option B (fail closed): all requests rejected. Customers outraged.
Neither is acceptable for a production API without a fallback.
Mitigation: fall back to per-region counting during outage.
Accept overdraft. This is a reasonable degraded mode.

Task 2 — Option B: Token bucket with 10-second sync:

Architecture:
Each region has a local Redis counter.
Every 10 seconds: each region sends its count delta to the other regions.
Regions aggregate: total_count = local_count + delta_from_us + delta_from_eu + delta_from_ap.
If total_count > 1,000: block the request.

Worst-case overdraft calculation:
During the sync interval (10 seconds), a bot makes max requests to each region:
US-East: 1,000 × (10/60) = 167 requests in the 10-second window.
EU-West: 167 requests.
AP-Tokyo: 167 requests.
Total: 501 requests in 10 seconds.
Per-minute limit is 1,000. In 10 seconds, the limit is 167.
Overdraft: 501 - 167 = 334 extra requests.
Overdraft percentage: 334 / 167 = 200% overdraft in a 10-second window.

That is way above 5% overdraft for a payment API.

Reduce sync interval to 1 second:
Each region can overdraft: 3 × (1,000 × 1/60) = 50 extra requests.
50 / 16.7 (per-second limit) = 300% overdraft per second.
Still bad. Token bucket with cross-region sync is fundamentally
limited by the sync interval.

This approach is acceptable only for search/content APIs
where small overdraft is tolerable.

Task 3 — Option C: Hash-based ownership:

Architecture:
hash(user_id) % 3 determines the "owning" region.
- user_id 12345 → hash → owned by US-East
- user_id 67890 → hash → owned by EU-West
- user_id 99999 → hash → owned by AP-Tokyo

Every request for a user_id — regardless of which region received it —
makes a rate limit check to the owning region for that user_id.

Latency overhead:
- Request received at the owning region: 0 extra latency.
- Request received at a non-owning region: +1 cross-region hop.
  EU to US-East: +75ms.
  AP to US-East: +150ms.
  But: only the rate limit check goes cross-region.
  The actual request processing stays local.
  So: +75–150ms added to requests going to non-owning regions.

On average: 2/3 of requests are not at the owning region.
Average extra latency = (0 + 75 + 150) / 3 = 75ms per request.

Still problematic for a < 10ms requirement.

Mitigation: cache the rate limit decision locally for 100ms.
If a user_id was allowed 100ms ago: allow them again.
This reduces the cross-region call frequency by 90%.
At 1,000 RPS per user: 100ms cache = only 10 cross-region calls/second per user.
Effective latency overhead: < 5ms amortized.
Overdraft window: 100ms. At 1,000 RPM: 100ms allows 1.67 extra requests.
Overdraft: ~0.17%. Well within 5%.

Failure mode if owning region goes down:
Options:
(a) Fail open: allow all requests. Bot gets through temporarily.
(b) Fail to a backup counter in another region.
  Pre-replicate the counter to a "shadow" region. Use shadow on failure.
  Overdraft risk during the failover window (seconds).

Task 4 — Which option for which API:

Payment API → Option C with local caching.

Reason:
Payments are high-stakes. A bot making 1,200 charge attempts per minute
instead of 1,000 is a real fraud risk.
Option C is deterministic (same region always owns the counter) and accurate.
With 100ms local caching: overdraft is < 0.2%. Acceptable for payments.
The cross-region hop latency is acceptable: payment requests
already take 200–500ms end-to-end (DB write, payment processor call).
Adding 75ms for rate limiting is < 20% overhead.

Search API → Option B with 2-second sync.

Reason:
Search has no financial consequence for overdraft.
A user making 1,100 search calls per minute instead of 1,000
is a minor abuse, not a fraud risk.
Option B adds 0ms extra latency per request (fully local counting).
This matters for search: search P99 SLA is often < 200ms.
Adding 75ms for a cross-region rate limit call is a 37% overhead.
Unacceptable.
Accept the 10–15% overdraft in exchange for 0ms latency overhead.

Task 5 — Redis sorted set sliding window:

Data structure:
Key: `rate:user:12345`
Type: Sorted Set
Score: request timestamp in milliseconds
Value: unique request UUID (prevents score collisions)

Commands per request:
```
now_ms = current_time_in_milliseconds()
window_start = now_ms - 60000  (60 seconds ago)

ZADD rate:user:12345 now_ms <request_uuid>
ZREMRANGEBYSCORE rate:user:12345 0 window_start
count = ZCARD rate:user:12345

if count > 1000:
    reject the request (429 Too Many Requests)
else:
    allow the request
```

Time complexity:
- ZADD: O(log N) where N = number of requests in the current window
- ZREMRANGEBYSCORE: O(log N + M) where M = number of entries removed
- ZCARD: O(1)
- Total: O(log N) per request

Practical N: at 1,000 requests/minute, N ≤ 1,000 at any time.
log(1000) ≈ 10 operations. Essentially constant time.

TTL management:
Set `EXPIRE rate:user:12345 120` after each ZADD.
If user is inactive for 120 seconds: key is automatically deleted.
Prevents memory leak from abandoned keys.

---

## 4. Quick Reference Card

---

### Multi-Region Decision Framework

Use this table before committing to full multi-region.

| Question | If YES → |
|----------|----------|
| Can CDN or regional caching solve the latency problem? | Use CDN + read replicas. Not full multi-region. |
| Is RTO > 5 minutes acceptable for your SLA? | Single-region + multi-AZ is sufficient. |
| Must writes be accepted locally in all regions? | Active-active (design conflict resolution first). |
| Does EU data legally need to stay in EU? | Separate EU primary + US primary (no cross-region data flow). |
| Is budget < 2× your current infrastructure cost? | Active-passive only. Active-active requires full fleet × N regions. |
| Are you a startup with < 5M users? | Single region. Multi-AZ. Save multi-region for later. |

---

### Key Numbers to Memorize for Interviews

These numbers should come out fluently.

An interviewer will notice if you have to calculate them.

| Metric | Value |
|--------|-------|
| NYC to London round-trip (physical minimum) | ~56ms (speed of light) |
| NYC to London round-trip (real-world AWS) | ~75ms |
| NYC to Tokyo round-trip (real-world AWS) | ~150ms |
| NYC to Singapore round-trip (real-world AWS) | ~175ms |
| Async replication lag — healthy | 10ms to 2 seconds |
| Async replication lag — degraded | 10 seconds to minutes |
| Semi-sync replication write overhead | 1 × cross-region RTT |
| DNS TTL for fast failover | 30–60 seconds (must be pre-set) |
| Active-passive RTO — automated with STONITH | 30 seconds to 2 minutes |
| Active-passive RTO — manual with runbook | 5 to 30 minutes |
| Active-passive RPO — async replication | 5 to 30 seconds |
| Active-passive RPO — semi-sync | < 1 second |
| Infrastructure cost multiplier: 1 → 3 regions | 2.5× to 3× |
| AWS cross-region data transfer cost | $0.02/GB |
| Spot instance savings vs on-demand | 60–70% |
| Reserved instance savings (1-year) | 30–40% |

---

### Replication Model Cheat Sheet

| Model | Who accepts writes? | Conflicts? | Split-brain risk | Best for |
|-------|---------------------|------------|-----------------|----------|
| Active-Passive | Primary only | None | Low (STONITH required) | Most transactional systems |
| Active-Active | All regions | Yes — must design resolution | High without careful design | CRDTs, append-only logs |
| Read-local / Write-central | Central primary | None | None | Read-heavy systems with write tolerance |
| Multi-Primary (geographic sharding) | One primary per user region | None (shards are disjoint) | Low | GDPR partitioned data |

---

### Consistency Model Cheat Sheet

| Consistency Model | What it means | Good for |
|-------------------|--------------|----------|
| Strong (linearizable) | All reads see the latest write | Balances, inventory, auth |
| Read-your-writes | You always see your own writes | Post submission, profile update |
| Monotonic reads | You never see older data on a re-read | Feed refresh, timeline |
| Eventual consistency | Replicas catch up asynchronously | Like counts, view counters |
| Causal consistency | Causally related writes are ordered | Messaging, threaded comments |

---

### Common Interview Red Flags

These responses lose points with L6 interviewers.

Avoid all of them.

- "Just add more regions for more availability."

  Reality: more regions = more failure modes, not fewer.
  Each region is a new source of partial failures.
  The relationship between regions and availability is not linear.

- "We'll use eventual consistency everywhere."

  Reality: financial balances, inventory, and auth
  require strong consistency.
  Saying "eventual consistency" without specifying WHICH
  operations can tolerate it shows imprecision.

- "Automatic failover handles everything."

  Reality: automatic failover without STONITH will eventually
  produce a split-brain at 3 AM.
  "Automatic failover" is not a complete answer.
  "Automated detection + STONITH + automated promotion" is.

- "Active-active is more modern / better than active-passive."

  Reality: active-active requires conflict resolution.
  For a payment system, "conflict resolution" means
  deciding which of two conflicting charge records is correct.
  That is an extremely hard problem.
  Active-passive is not inferior — it is simpler and safer
  for most transactional use cases.

- "Cross-region latency is negligible."

  Reality: 75ms × 10,000 writes/second = every write thread
  holds a connection for 75ms.
  This is not negligible. This requires careful capacity planning.

- "We'll replicate everything in real-time."

  Reality: "real-time" replication at scale means
  choosing between: write latency overhead (sync),
  potential data loss (async), or complex conflict resolution (active-active).
  "Real-time" is not a replication strategy. It is a wish.

---

### Failover Runbook Template

Keep this mental model for any active-passive failover question.

Step 1: Confirm.
  Require N consecutive failures over T seconds from M independent probes.
  Do not fail over on a single spike.

Step 2: Alert.
  Page on-call. Even for automated failover, a human must know.

Step 3: STONITH.
  Fence the primary BEFORE promoting the replica.
  This is mandatory. No exceptions.

Step 4: Promote.
  Promote the replica to primary.
  Verify promotion completed successfully before proceeding.

Step 5: Reconfigure.
  Update application config (DB host).
  Update load balancer target groups.
  Trigger config reload or rolling restart of application servers.

Step 6: DNS.
  Update DNS TTL (must already be < 60 seconds before an incident).
  Update the DNS record to point to new region.
  Wait for TTL to expire.

Step 7: Verify.
  Run a synthetic end-to-end transaction.
  Confirm error rates are back to normal baseline.
  Confirm DB write latency is normal.

Step 8: Document.
  Log the failover time, duration, and RPO achieved.
  Open a post-mortem ticket.

---

*End of Chapter 36 — Part F*

*This is the final section of Chapter 36: Multi-Region Systems.*
## Supplemental Brainstorming: Chapter 36 -- Multi-Region Systems

*Questions 35-49: Advanced patterns and cross-chapter integration.*

---

### Section A: Advanced Multi-Region Patterns (Q35-Q41)

---

**Question 35 -- Active-active conflict resolution: CRDTs in practice**

Your multi-region active-active system allows users to edit their profile in any region. A user updates their display name from "Alice" to "Alice Smith" in us-east-1 at T=100ms and also updates it to "Alice M." in eu-west-1 at T=110ms (clocks are not perfectly synchronized). Both writes succeed locally. When replication happens, both regions have conflicting values. Design the conflict resolution strategy.

- Last-Write-Wins (LWW) is the simplest strategy: compare timestamps, keep the later one. The problem is clock skew. If eu-west-1's clock is 50ms ahead, "Alice M." at T=110ms appears to be later than "Alice Smith" at T=100ms even though Alice intended "Alice Smith" to be her final choice. LWW silently discards one write based on potentially incorrect clocks. Use hybrid logical clocks (HLC) to mitigate this: HLC combines physical time with a logical counter, ensuring causally later events have higher timestamps.
- CRDTs (Conflict-free Replicated Data Types) resolve conflicts without coordination. For a display name field, a CRDT approach is a Multi-Value Register (MVR): instead of discarding one value, keep both conflicting values and surface the conflict to the user ("We noticed you updated your profile in two places. Which name do you prefer?"). This is how Dynamo-style systems handle write conflicts.
- Application-level merge: if the business rule is "latest wins for name, but merge for preferences," implement custom merge logic in the application layer. Each object carries a vector clock. On conflict, the application compares vector clocks to determine which write causally happened after the other. If neither dominates (concurrent writes), apply the merge rule.
- Follow-up: You decide to use LWW with HLC for user profile updates. A malicious user discovers they can forge a high-timestamp write to overwrite another user's profile. How does your system prevent timestamp forgery in a distributed active-active system?

---

**Question 36 -- Single global leader with Spanner/CockroachDB**

Your team is considering replacing your custom multi-region replication (PostgreSQL primary in us-east-1 + read replicas in eu-west-1 + ap-southeast-1) with CockroachDB or Google Cloud Spanner. Both offer globally distributed SQL with serializable consistency. Explain the architectural difference and when globally distributed SQL is worth the cost and complexity.

- Traditional PostgreSQL multi-region: one primary handles all writes, replicas handle reads. Cross-region writes go to us-east-1 (which could mean 150ms round trip for EU users writing data). Failover is manual or semi-automated. Schema changes require careful coordination. The system is simple and well-understood, but it concentrates write load and introduces write latency for distant users.
- CockroachDB / Spanner: uses a distributed consensus algorithm (Raft in CockroachDB, Paxos in Spanner) to keep all nodes consistent without a single primary. Any node can serve writes. Writes are serializable globally: if a transaction writes to data whose Raft leader is in us-east-1, the write still requires a Raft quorum (2 of 3 nodes), which means at least one cross-region round trip for EU writes to us-east-1 data. Locality pinning (CockroachDB's LOCALITY setting) pins each row's Raft leader to the region where that user lives, making writes local.
- Worth the cost when: you need serializable consistency globally (banking, inventory), you need zero-downtime regional failover, or your writes are geographically distributed and you cannot tolerate cross-region write latency. Not worth the cost when: your write load is concentrated in one region, your queries are mostly reads (read replicas are sufficient), or your team lacks distributed systems expertise to operate it.
- Follow-up: Spanner charges for "processing units" (compute) plus storage plus "TrueTime API" overhead. Estimate the monthly cost of Spanner for a 500GB database with 1,000 write transactions per second distributed globally, and compare to an equivalent Aurora PostgreSQL setup with two read replicas.

---

**Question 37 -- Chaos engineering for multi-region failure simulation**

Your multi-region active-active system has never experienced a real region failure. Your SRE team wants to validate that failover actually works as designed before a real outage happens. Design a chaos engineering program for multi-region failure testing.

- Start with hypothesis-driven experiments: before running any chaos, state the expected behavior. "If us-east-1 loses network connectivity to eu-west-1 for 60 seconds, we expect: (a) EU users continue to be served by eu-west-1 with local reads, (b) cross-region writes fail gracefully with a user-visible error or are queued, (c) monitoring alerts fire within 30 seconds, (d) the system returns to normal within 5 minutes of connectivity restoration."
- Failure injection tools: AWS Fault Injection Simulator (FIS) can: block all traffic between regions (simulating a network partition), terminate EC2 instances in a specific AZ, inject latency on specific API calls, or throttle DynamoDB read/write capacity. Start with small blast radius (inject failure on 1% of traffic) before simulating a full region failure.
- Game days: run a scheduled chaos experiment where the on-call team is notified 1 hour before and must respond as if it were a real outage. Measure: time to detection (TTD), time to mitigation (TTM), whether runbooks are accurate, and whether monitoring surfaced the right signals. Document gaps and fix them before the next game day.
- Follow-up: During a chaos experiment, you simulate a network partition between us-east-1 and eu-west-1. You observe that eu-west-1 continues to serve reads correctly but writes fail silently (no user error, no alert). The writes are being dropped. What went wrong, and how do you fix both the bug and the monitoring gap?

---

**Question 38 -- Latency budgeting for multi-region requests**

Your multi-region system has a user-facing API with a P99 latency SLA of 200ms. The request involves: an authentication check (Redis session lookup), a database read (user profile), and a downstream service call (recommendation service). In your EU region, these three components have latencies of 12ms, 45ms, and 80ms respectively. The P99 tail adds 3x overhead. Design the latency budget and identify where multi-region architecture introduces latency risk.

- Latency budget allocation: total budget 200ms P99. Baseline P50 latency: 12 + 45 + 80 = 137ms. P99 with 3x tail: 137ms x 1.5 (realistic tail factor for independent services, not multiplicative) = ~200ms. This is already at the SLA limit with zero margin. You need to cut at least 40ms from the baseline to have a safe P99.
- Multi-region latency risk: if the Redis session store is in us-east-1 and the EU user's request hits eu-west-1, the session lookup crosses the Atlantic (80-100ms round trip). This single cross-region dependency blows the 200ms budget immediately. Every service dependency must have a regional instance; no cross-region synchronous calls are allowed on the critical path.
- Latency budget enforcement in practice: instrument every service call with distributed tracing (OpenTelemetry). Set span budgets: if the Redis call takes longer than 15ms P99, alert. If the DB read takes longer than 50ms P99, alert. Use circuit breakers with aggressive timeouts (Redis timeout: 20ms, DB timeout: 60ms, recommendation timeout: 100ms). Fail fast rather than queue. Return a degraded response (no recommendation) rather than wait for the recommendation service.
- Follow-up: Your P99 latency is 195ms in EU and 180ms in US. You add a third region (ap-southeast-1) and discover P99 is 320ms there. Investigation shows the auth service has no AP replica and falls back to eu-west-1. How do you identify all such cross-region synchronous dependencies systematically across 47 microservices?

---

**Question 39 -- DNS failover timing and the TTL problem**

Your multi-region system uses Route 53 (AWS) for global DNS routing with health checks. Each region has an API endpoint (api.us.example.com, api.eu.example.com) behind a global alias (api.example.com). The TTL on the DNS record is 300 seconds (5 minutes). When us-east-1 fails, Route 53 stops routing traffic there. How long until all clients failover, and why is DNS-based failover fundamentally limited?

- DNS failover timing breakdown: Route 53 runs health checks every 10 seconds and declares a region unhealthy after 3 consecutive failures (30 seconds). Once unhealthy, Route 53 stops returning the failed endpoint's IP. But clients have already cached the old DNS response for up to 300 seconds (the TTL). A client that cached the DNS response 1 second before the failure occurs will keep trying the failed endpoint for 299 more seconds.
- The TTL problem: you cannot guarantee all clients fail over within the TTL window. Some clients (especially mobile apps, embedded devices, corporate proxies) ignore or cap the TTL. A client that cached the IP and ignores TTL will attempt to connect to the dead region indefinitely. DNS failover is probabilistic and time-bounded, not instantaneous.
- Mitigation: reduce the TTL to 60 seconds (at the cost of higher DNS query load and slightly higher latency for the first request). Combine DNS failover with client-side retry with backoff: if the primary endpoint returns a connection timeout, the client immediately retries with a secondary endpoint hardcoded in the client. This eliminates the TTL dependency for failover. Use anycast IP routing (AWS Global Accelerator) to route at the network layer (BGP) rather than DNS layer -- failover happens in seconds, not minutes.
- Follow-up: A client has cached the IP of us-east-1's load balancer. us-east-1 fails. The load balancer's IP is now unreachable. The client's TCP connection attempt times out after 30 seconds (the OS TCP connect timeout). The client retries 3 times. Total time before the client gives up and your application error handler kicks in: 90 seconds minimum. How do you reduce this to under 5 seconds using client-side socket timeouts?

---

**Question 40 -- Global load balancer health checks and failover triggers**

You use AWS Global Accelerator (anycast IP routing) in front of your multi-region system. Global Accelerator runs health checks against each regional ALB every 10 seconds. Your us-east-1 region is experiencing a "brown-out": the API responds to health checks (200 OK) but actual user requests are failing at a 40% error rate due to a database connection pool exhaustion. Design a more sophisticated health check that detects brown-out conditions.

- Shallow health checks (GET /health returning 200 OK) do not detect brown-outs. The health endpoint responds from a lightweight in-process handler that does not exercise the database or downstream services. You need a deep health check (GET /health/deep) that: attempts to acquire a DB connection from the pool (and times out in 500ms if the pool is exhausted), makes a test read to the primary DB, and checks that the Redis cache is reachable.
- The risk of deep health checks: they can be expensive at scale (10 health checks per second x 3 load balancers x 50 deep checks per ALB = a lot of DB connections just for health checking). Mitigate by making the deep check use a dedicated health-check connection pool separate from the main application pool, or by caching the health check result for 5 seconds (the check runs async and the endpoint returns the cached result).
- Synthetic monitoring: run a canary (a real synthetic user transaction) every 30 seconds from each region. The canary logs in, fetches a profile, and makes a write. If the canary fails, trigger a health-check failure programmatically via the AWS API. This detects user-impacting failures that bypass shallow or even deep health checks (e.g., auth service is healthy but returns wrong session tokens).
- Follow-up: Global Accelerator removes a region from rotation when health checks fail. The region's DB connection pool has recovered. How do you re-add the region to rotation safely? If you add it immediately, it gets 33% of traffic instantly (from near 0%). Is that safe? How do you implement a traffic warm-up ramp?

---

**Question 41 -- Multi-region data consistency model selection**

You are designing a new feature: a user's "follower count" displayed on their profile. The count must be visible globally. You have three options: (A) strong consistency (every read sees the latest write, requires cross-region coordination), (B) eventual consistency (reads may see stale counts, updates propagate asynchronously), (C) causal consistency (a user who just incremented their follower count sees the updated count on their next read). Analyze each option for a social media profile use case.

- Option A (strong consistency): requires that every read goes through a global consensus protocol (Spanner TrueTime, CockroachDB Raft). For follower count, this means every profile page load must wait for a cross-region round trip to confirm the latest count. For users in ap-southeast-1 reading data whose leader is in us-east-1, this adds 200ms to every profile load. Unacceptable for a high-traffic, latency-sensitive feature.
- Option B (eventual consistency): follower count is replicated asynchronously. A profile loaded in eu-west-1 may show a count that is 5 seconds stale. For follower counts (which users check to see approximate social proof, not exact numbers), 5 seconds of staleness is entirely acceptable. This is the correct model for this use case. Implement using DynamoDB Global Tables or Cassandra multi-region replication.
- Option C (causal consistency): a user who just gained a new follower sees the count increment on their next page load, even if they load from a different region. This requires session-level causality tracking (vector clocks per session or monotonic reads per user session). More complex than eventual consistency, but better UX than pure eventual. Implemented in MongoDB with causal sessions or in Cassandra with client-side session tokens.
- Follow-up: The product team says follower counts must be accurate to within 1% for users with more than 1M followers (because they are shown in branded partnership agreements). Does this change your consistency model choice? How do you serve both high-traffic casual users (eventual OK) and verified high-follower accounts (stronger consistency) from the same system?

---

### Section B: Cross-Chapter Integration (Q42-Q49)

---

**Question 42 -- Ch36 + Ch28: CockroachDB vs PostgreSQL with regional primaries**

You run PostgreSQL with a primary in us-east-1 and read replicas in eu-west-1 and ap-southeast-1. Your EU team complains about 180ms write latency (cross-Atlantic to the primary). You are evaluating CockroachDB as a replacement. Compare the two architectures for a B2B SaaS application with 80% read traffic and 20% write traffic, 500GB of data, and strict serializable isolation requirements.

- PostgreSQL multi-region current state: reads are served locally from replicas (fast). Writes go to us-east-1 primary (slow for EU and AP). Failover requires promoting a replica, which is a manual or semi-automated process taking 2-5 minutes. Schema changes must be coordinated to not break replication. Operational complexity is manageable because PostgreSQL is well-understood.
- CockroachDB: with locality pinning, rows belonging to EU accounts have their Raft leader in eu-west-1. EU writes to EU data are local (fast). EU writes to US data still require cross-region consensus. The application must annotate rows with locality hints. CockroachDB's serializable isolation is guaranteed globally without application-level conflict detection. Failover is automatic (Raft elects a new leader in seconds).
- Cost and complexity: CockroachDB requires a minimum of 3 nodes per region (9 nodes total for 3 regions) for proper Raft quorums. CockroachDB Enterprise licenses add significant cost. PostgreSQL with managed Aurora Global Database is cheaper and simpler for a 500GB, primarily-read workload. CockroachDB is worth it when write locality matters for EU/AP users and when automatic failover is a hard requirement.
- Follow-up: Your SaaS application has a "tenant isolation" requirement: each customer's data must be queryable independently for their own analytics. How does tenant-based row locality pinning in CockroachDB interact with cross-tenant analytics queries (which must read from all regions)?

---

**Question 43 -- Ch36 + Ch31: Multi-region session management**

EU users of your SaaS application experience 150ms session lookup latency because the Redis session store is only in us-east-1. When a session is created in eu-west-1, it is stored in us-east-1. Every request from an EU user crosses the Atlantic for the session lookup. Design the multi-region session architecture, including how to handle session consistency when a user switches regions mid-session (e.g., a traveler lands in the US and continues their session).

- Solution 1: Regional Redis clusters with session affinity. Deploy a Redis cluster in each region. When a session is created, it is stored in the regional Redis of the user's current region. The load balancer uses geolocation-based routing to always send the user to their home region's cluster. EU users hit eu-west-1 Redis. Session lookups are local (sub-millisecond). Cross-region consistency is not needed as long as the user stays in their region.
- The traveler problem: a user creates a session in eu-west-1 (session ID: abc123). They board a flight. Their laptop connects from the US. Route 53 now routes them to us-east-1. Session abc123 does not exist in us-east-1's Redis. The user appears logged out. Options: (a) replicate sessions to all regions on creation (expensive, high write amplification), (b) fall back to the origin region (us-east-1 proxies the session lookup to eu-west-1), (c) re-authenticate the user silently using a long-lived cookie and issue a new session in us-east-1.
- Option (c) is most practical: use a short-lived session token (15 minutes) plus a long-lived refresh token stored in an HttpOnly cookie. When the session token is missing or expired, the client presents the refresh token. The server validates the refresh token against a globally replicated (low-write, high-read) token store (DynamoDB Global Tables) and issues a new session in the current region. The traveler gets a seamless re-auth in under 200ms.
- Follow-up: The refresh token store uses DynamoDB Global Tables with eventual consistency. A user's refresh token is revoked (logout on device A) in eu-west-1. 30 seconds later, the user tries to use the same refresh token from device B in us-east-1. Due to replication lag, us-east-1 still sees the token as valid. How do you prevent this "revocation lag" from being a security hole?

---

**Question 44 -- Ch36 + Ch33: Multi-region Kafka: MirrorMaker 2 vs Confluent multi-region clusters**

Your event-driven system uses Kafka. You need Kafka topics to be available in both us-east-1 and eu-west-1 for disaster recovery and for GDPR-compliant regional processing. Compare MirrorMaker 2 (open source) and Confluent Platform's multi-region clusters (commercial). State the RPO and RTO for each.

- MirrorMaker 2 (MM2): an open-source Kafka-to-Kafka replication tool based on Kafka Connect. It runs as a Kafka Connect cluster in the destination region and consumes from the source cluster, writing messages to mirrored topics in the destination. RPO is typically 5-30 seconds (the replication lag). RTO is the time to update DNS/load balancer routing to point producers and consumers at the DR cluster: 1-5 minutes with automation. MM2 renames mirrored topics (us-east-1.my-topic) so consumers must know which cluster they are consuming from.
- Confluent Multi-Region Clusters (MRC): a commercial feature where a single Kafka cluster spans multiple regions. Topics have "observers" (async replicas) in remote regions and "replicas" (synchronous) in the local region. You can promote an observer to a full replica without consumer group offset resets. RPO for observers: seconds to minutes (async). RPO for synchronous replicas: 0 (but synchronous cross-region replication adds write latency). RTO: seconds (promote observer to leader, consumers reconnect to same cluster).
- The key difference: MM2 creates a separate cluster in each region (separate consumer group offsets, separate topic names). Failover requires consumers to reset offsets. MRC keeps one logical cluster across regions; failover is transparent to consumers. For GDPR, MM2 lets you keep EU topics on physically separate EU brokers. MRC requires careful configuration to ensure EU data does not land on US brokers.
- Follow-up: With MM2, a consumer group in eu-west-1 is at offset 1,000,000 on the mirrored topic. The source cluster (us-east-1) fails. You promote the eu-west-1 mirrored topic to the new source. The consumer resumes at offset 1,000,000. But MM2's mirrored offsets do not map 1:1 to the source offsets. How does MM2's RemoteClusterUtils.translateOffsets handle offset translation, and what is the risk of missing messages?

---

**Question 45 -- Ch36 + Ch37: GDPR-compliant global reads of EU user data**

You are building a multi-region system that must comply with GDPR (EU user data stays in EU) but also provide low-latency reads globally. EU users' raw PII (email, name, address) cannot leave the EU. However, non-EU users need to see EU users' public profiles (username, profile photo, follower count). Design the architecture that satisfies both constraints simultaneously.

- Data classification is the first step. Split the EU user's data into two categories: (a) PII data (email, phone, address, behavioral logs) -- must stay in EU, (b) public profile data (username, profile photo URL, follower count, bio) -- this is user-chosen public information, not PII. Public profile data can be served globally.
- Architecture: store PII in an EU-only database (Aurora in eu-west-1, no cross-region replication). Store public profile data in a globally replicated store (DynamoDB Global Tables, replicating to us-east-1 and ap-southeast-1). When a US user loads an EU user's public profile, the request hits us-east-1's DynamoDB replica -- no EU infrastructure is touched.
- Profile photo CDN: profile photos are public user-chosen content, not PII. They can be served from a global CDN (CloudFront). However, if photos contain biometric data (faces), some GDPR interpretations classify them as biometric data (a special category). Legal review needed. If classified as PII, serve photos only from an EU CDN edge node, restricting caching to EU POP locations.
- Follow-up: An EU user changes their username. The change must propagate to the globally replicated public profile store. DynamoDB Global Tables has replication lag of 1-2 seconds. A US user loads the EU user's profile 500ms after the change -- they see the old username. Is this acceptable? What if the EU user just changed their username to distance themselves from a harmful incident (e.g., they were doxxed)? Does the UX and latency requirement change?

---

**Question 46 -- Ch36 + Ch38: Total cost of ownership for a 3-region active-active system**

Your multi-region system runs in us-east-1, eu-west-1, and ap-southeast-1. Monthly infrastructure per region: $60,000 (compute, storage, managed services). Cross-region replication traffic: 500GB per day per region pair (3 pairs = 1.5TB per day total). AWS data transfer out pricing: $0.09/GB for first 10TB/month. Calculate the total monthly infrastructure cost and the percentage overhead of going from 1 region to 3 regions.

- Compute cost: $60,000 x 3 regions = $180,000/month. Data transfer cost: 1.5TB/day x 30 days = 45TB/month. First 10TB at $0.09/GB = $900. Next 35TB at $0.085/GB (next tier) = $2,975. Total data transfer = ~$3,875/month. Additional costs: Route 53 latency-based routing queries, Global Accelerator ($0.025 per accelerator hour + data transfer), cross-region CloudWatch metrics, inter-region VPC peering data transfer ($0.02/GB within AWS backbone) for internal traffic.
- Total monthly estimate: $180,000 (compute) + $3,875 (internet data transfer) + ~$2,000 (internal cross-region replication via VPC peering at 45TB x $0.02/GB) + ~$500 (Global Accelerator, Route 53) = ~$186,375/month. A single-region system costs $60,000/month. 3 regions costs 3.1x more. The "multi-region overhead" beyond raw duplication: 3.1x - 3.0x base = roughly 3-5% overhead from cross-region traffic and global services.
- Business justification: the cost of 3 regions vs 1 region is $126,375/month in additional spend. At what point does this become worth it? Calculate against: expected revenue loss per hour of downtime, regulatory requirement (GDPR mandates EU data residency regardless of cost), competitive requirement (customers in AP demand low-latency SLA).
- Follow-up: Your CTO says "can we save money by making AP a read-only region instead of active-active?" Calculate the cost of an active-passive AP region where you only replicate reads (no write traffic to AP, 200GB/day instead of 500GB/day). How much do you save, and what is the UX impact on AP users who now have to cross to us-east-1 for every write?

---

**Question 47 -- Ch36 synthesis: designing for regional isolation without losing global consistency**

You are the architect of a financial trading platform. Regulatory requirements mandate that US trade data stays in the US and EU trade data stays in the EU. However, a single user account can be used to trade in both markets. A user's margin balance (available capital) must be consistent globally: if they use $50,000 of margin for a US trade, their EU trading session must immediately see $50,000 less available margin. Design this system.

- The tension: data residency says EU trade data stays in EU and US trade data stays in US. Global consistency says the margin balance (a shared resource) must be consistent across regions. These two requirements create a fundamental conflict: to enforce global margin consistency, you need a cross-region transaction.
- Solution: separate the margin balance account from the individual trade records. The margin balance is a single global entity that does not belong to either region's trade data (it is financial data, not trade log data). Store the margin balance in a globally distributed strongly consistent database (Spanner or CockroachDB) that serves as the authoritative source. Individual trade logs are stored in their respective regional databases (US trades in us-east-1, EU trades in eu-west-1). The trade log is regional. The balance is global.
- Trade execution flow: when a US trade is executed, the trade system does a two-phase commit: (1) deduct margin from the global balance (Spanner transaction), (2) write the trade record to the US regional database. If step 2 fails, roll back step 1. The global balance is always authoritative. EU and US trading sessions both read from the global balance.
- Follow-up: Spanner's global transactions add 10-30ms latency for the cross-region consensus on the margin balance deduction. In high-frequency trading, 10ms is unacceptable. How do you design a pre-authorization system that locks a portion of margin locally (allowing fast execution) while the global balance is settled asynchronously?

---

**Question 48 -- Ch36 synthesis: region-to-region failover runbook**

Your active-passive multi-region system has us-east-1 as primary and eu-west-1 as standby. A total failure of us-east-1 occurs at 2:17 AM. Your on-call engineer must execute a failover to eu-west-1. Walk through the complete failover runbook, including estimated time for each step and the decisions that cannot be automated.

- Step 1 (0-2 minutes): Confirm the failure. Verify us-east-1 is actually down (not a monitoring false alarm). Check CloudWatch dashboards, check from an independent vantage point (an EC2 instance in eu-west-1 trying to reach us-east-1 endpoints), check AWS Service Health Dashboard. Do not start failover on a false alarm -- a misfire causes unnecessary risk. This step requires human judgment.
- Step 2 (2-5 minutes): Assess data loss. Check the replication lag at the time of failure. If eu-west-1 is 30 seconds behind us-east-1, there are ~30 seconds of transactions that were committed in us-east-1 but not replicated to eu-west-1. Decide: is the business impact of losing 30 seconds of transactions acceptable, or do you wait for recovery? This is a business decision, not a technical one. The on-call must escalate to a business owner.
- Step 3 (5-10 minutes): Promote eu-west-1 to primary. Run the promotion script: promote the Aurora read replica to primary (3-5 minutes), update Route 53 DNS records to point api.example.com to eu-west-1 load balancer (DNS change takes effect based on TTL -- 60-300 seconds), update any hardcoded primary endpoints in configuration (ideally done via parameter store, one change propagates to all services).
- Step 4 (10-20 minutes): Validate the promotion. Run the synthetic canary against eu-west-1 endpoints. Verify writes succeed. Verify reads return consistent data. Verify the queue drains. Communicate status to stakeholders.
- Follow-up: After 45 minutes, us-east-1 comes back online. Now you have two "primaries" with diverged data. eu-west-1 has 45 minutes of new writes. us-east-1 has the pre-failure data plus potentially some writes that were in-flight during the failure. How do you merge them? This is the failback problem -- why is failback often harder than failover?

---

**Question 49 -- Ch36 synthesis: testing multi-region RTO and RPO before they matter**

Your SLA guarantees RTO of 15 minutes and RPO of 1 minute for a regional failure. You have never tested these in production. Your CTO wants proof that these SLAs are achievable before the next annual customer audit. Design a testing program that validates RTO and RPO claims without risking production data.

- RPO test (data loss measurement): at a known time T, inject a marker transaction ("sentinel write") into the primary region. Immediately simulate a primary failure (block replication, then checkpoint the standby). Measure: is the sentinel write present in the standby? How many subsequent transactions are present? The time gap between the last replicated transaction and T is your actual RPO. Do this test monthly with 5-minute, 1-minute, and 30-second RPO targets to build a data series.
- RTO test (recovery time measurement): in a staging environment that mirrors production (same infrastructure, same runbook), execute the complete failover runbook with a stopwatch. Measure time for each step. Identify which steps are manual (and therefore variable) and which are automated. The sum of all steps is your measured RTO. If the measured RTO is 22 minutes and your SLA says 15 minutes, you have a gap to close before the audit.
- Production shadow test: instead of a full failover, test the failover to the standby in parallel without switching traffic. Promote the standby to "mock primary" in a shadow environment, run read-only validation against it, then demote it back. This validates that the promotion procedure works without disrupting users. Route 53 health check response can be tested by temporarily marking a region unhealthy in a non-production health check group.
- Follow-up: Your CTO wants the failover to be fully automated (no human in the loop) to guarantee the 15-minute RTO. What are the risks of fully automated regional failover, and what safeguards prevent an automated failover from triggering on a false alarm (a 30-second CloudWatch blip rather than a real regional failure)?

---


---

### Cross-chapter: etcd multi-region quorum topology (from Ch22)

**Question 45 -- etcd topology for multi-region quorum tolerance (Ch22 + Ch36)**

5-node etcd cluster. Raft quorum: 3 of 5. Topology: US-East (E1, E2), US-West (W1, W2), EU-West (EU1).

- Partition 1: US-East isolated. Remaining: W1, W2, EU1. Do they have quorum? Can they elect a leader and commit writes? What do E1 and E2 do?
- Partition 2: US-West isolated. Remaining: E1, E2, EU1. Quorum? Now add: EU1 crashes. Only E1 and E2 remain. Do they have quorum? What does etcd return when a client writes?
- A 3+3+1 = 7-node topology (quorum: 4 of 7) tolerates any single region failure. Prove it: walk through each case (lose US-East: 3 gone, 4 remain; lose US-West: 3 gone, 4 remain; lose EU-West: 1 gone, 6 remain).
- Follow-up: etcd supports "learner" nodes -- they replicate the log but do not vote. A learner in AP-Southeast-1 serves reads locally without affecting quorum. What consistency guarantee do learner reads provide? What do they NOT provide?

---

### Cross-chapter: Multi-region payment idempotency (from Ch23)

**Question 42 -- Multi-region idempotency for payments (Ch23 + Ch36)**

A payment request hits US-East (circuit breaker: open due to CPU spike).
The load balancer fails it over to EU-West. EU-West processes the payment successfully.
The client's HTTP client times out before receiving the response.
The client retries. The retry hits US-East (now recovered).
US-East has no record of the EU-West payment. US-East charges the card again.

- Identify the idempotency gap: this is not a retry bug or a database bug --
  it is a multi-region state isolation problem.
  What consistency model does the idempotency store need to prevent this?
  Strong consistency? Read-your-writes? Causal? Why is eventual consistency insufficient?
- Candidate global idempotency stores:
  (a) DynamoDB Global Tables: last-writer-wins, ~1 second replication lag.
  (b) Google Spanner: external consistency (linearizability), 10-20ms commit latency.
  (c) CockroachDB: serializable isolation, ~20-50ms cross-region commit latency.
  For each: does it prevent the double-charge scenario? At what latency cost per payment API call?
- Sticky routing as an alternative: hash idempotency_key to a region at the global load balancer.
  All retries for the same key go to the same region.
  What infrastructure component enforces this routing?
  What happens if the designated region is down -- fail open (route anywhere) or fail closed?
  What is the consequence of each for the double-charge problem?
- Follow-up: Stripe stores idempotency state in a globally replicated database.
  The extra 10-20ms write latency is the price of correctness.
  For a payment API with a p99 target of 500ms, how significant is 20ms overhead?
  What is the business argument for absorbing this cost
  vs accepting rare (1-in-100,000) duplicate charges?

---

### Cross-chapter: End-to-end payments resilience across multi-region (from Ch23)

**Question 45 -- End-to-end resilience design for a payments microservice (Ch23 + Ch28 + Ch36)**

Design the complete resilience stack for a payment microservice calling:
(1) Fraud Detection (critical, p99=100ms, max tolerable latency=300ms),
(2) Payment Processor API (critical, p99=500ms, idempotent, max tolerable=2000ms),
(3) Notification Service (non-critical, p99=200ms, fire-and-forget acceptable).

- Timeout and retry configuration for each dependency.
  Justify each timeout against the max tolerable latency constraint.
  For the Payment Processor: why must retries use the SAME idempotency key as the original?
  What happens if you generate a new UUID on each retry?
- Idempotency end-to-end: the client sends idempotency_key=K1.
  The payment service creates a derived key for the Processor:
  K1_processor = hash(K1 + "payment_processor").
  The payment service also stores K1 in its own idempotency table.
  On client retry with K1: the service finds K1 in its table (first attempt succeeded)
  and returns the cached response WITHOUT calling the Processor again.
  What does the service store alongside K1 to reconstruct the response?
  What if the first attempt is still in-flight (status: "pending")?
- Cascading failure: Fraud Detection becomes slow (p99=5 seconds).
  Walk through bulkhead filling, circuit breaker opening, and fallback activating.
  While the circuit is open, what does the service do:
  fail the payment (refuse to process without fraud check), or approve with degraded mode
  (log for async review)?
  Argue both positions from a risk perspective.
- Follow-up: Define the SLO: availability target (99.9%), error budget (0.1%),
  latency target (p99 < 2 seconds).
  If Fraud Detection's circuit is open for 10 minutes and the service processes payments
  without fraud checks, are those 10 minutes counted against the availability SLO?
  Argue: "the service was available (payments processed)" vs
  "the service was degraded (fraud checks bypassed = business error)."
  What does your SLO definition say?

---

### Cross-chapter from Ch20: Authentication Consistency in Active-Active

**Question 41 — Ch20 + Ch36: Authentication Consistency in Active-Active Multi-Region**

You run an active-active deployment in two regions: EU-West and US-East. Both regions accept reads and writes. Cross-region async replication has 200ms mean lag and 800ms P99. A user in London updates their password at EU-West's primary (time T=0). The new password hash is committed. At T+100ms, the user's mobile app sends an automatic session refresh request — cellular routing sends it to US-East. US-East's replica has not received the new password hash yet (still 100ms within the 200ms mean lag window). Authentication fails.

- List three distinct strategies to prevent this false authentication failure. For each strategy, describe the mechanism in two sentences, the latency cost in the normal case where no password change has occurred in the past 10 minutes, and the single most dangerous failure mode of that strategy.
- One strategy is to synchronously replicate only the authentication table (password hashes, MFA settings, session invalidation list) to all regions, while keeping all other data on async replication. The cross-region round-trip is 90ms. Current password change latency: 40ms. What is the new password change latency? How does this affect the user experience of changing a password, and is this latency acceptable for a security operation?
- A second strategy uses a globally-low-latency coordination service — similar to Cloudflare Workers KV or DynamoDB Global Tables — to store only the security-critical credentials. This service replicates in under 50ms P50 but up to 300ms P99.9. Your user attempts authentication at T+100ms. What is the probability that the credential store is not yet consistent at that moment? At T+500ms? At T+1000ms? What user-facing retry logic handles the small probability of failure at T+100ms?
- Follow-up: The user does not change their password — they disable two-factor authentication because their phone was stolen. The async lag means US-East still requires MFA for up to 200ms after the change. During those 200ms, the attacker using the stolen phone could authenticate with the old phone's MFA token. Is this window a meaningful security risk? What is the expected probability of an attacker exploiting a 200ms window? Does your answer change if MFA changes should be treated as security-critical and therefore synchronously replicated, even at 90ms additional latency?

> *Discussion notes:*
> - *Strategy 1 (synchronous cross-region for auth table): adds 90ms to password changes. Failure mode: during a partition between EU-West and US-East, password changes fail globally. Strong consistency for security writes creates an availability problem.*
> - *Strategy 2 (global credential store): failure mode is global scope — if the credential store degrades, all auth fails everywhere rather than just in one region. Requires extremely high availability SLA.*
> - *Strategy 3 (signed session token forwarding): the client carries a signed token with the write timestamp. US-East reads the token, detects a recent credential change, and escalates to the primary. Failure mode: token must be cryptographically signed to prevent forgery. If signing is skipped, an attacker can manufacture a token claiming any write timestamp.*
> - *The correct answer for most systems: strategy 2 (global credential store) scoped only to the authentication table, not the entire user database. This is what services like Auth0, Okta, and Firebase Auth do internally.*
> - *MFA 200ms window: not a meaningful risk in practice. An attacker must know the exact moment MFA was disabled AND send an auth request within 200ms. This combination requires real-time surveillance of the account. Synchronous replication for every MFA change is not justified by this risk at the typical threat model.*

---


### Cross-chapter from Ch20+Ch21: Password Update Across Three System Layers

**Question 45 — Ch20 + Ch36 + Ch21: The Password Update Across Three System Layers**

Setup: active-active multi-region deployment in EU-West and US-East. Within each region: one primary and two followers with async replication. Cross-region: async replication at 200ms mean lag. Authentication service reads user credentials from the nearest replica within its region.

Sequence of events: A user changes their password in a browser in London (EU-West) at 10:00:00.000 AM. The write commits on the EU-West primary. At 10:00:00.150 AM (150ms later), the user's iOS app, on a cellular connection that routes to US-East, sends an automatic session token refresh that requires re-verifying the password hash. At 10:00:00.500 AM, the cross-region replication lag catches up and US-East has the new password.

- At T+150ms: US-East's auth service queries its replica for the password hash. The replica received the new hash at approximately T+200ms (mean cross-region lag). At T+150ms, what does US-East return to the iOS app? Is this a system bug, a consistency model failure, or expected behavior under the configured async replication? Write the on-call runbook entry that distinguishes "expected behavior" from "system malfunction" for this symptom.
- Design the minimum change to prevent the T+150ms failure without synchronously replicating all password changes cross-region. What is your mechanism? What additional component does it require? What is the latency overhead on every password change (which happens once every few months per user) vs. every authentication request (which happens multiple times per day per user)?
- Your design introduces a "credential freshness token" stored in a globally-consistent key-value store. This store has 50ms P50 replication latency and 300ms P99.9. The user changes their password — the token is written at T=0, mean replication at T+50ms. The iOS app retry arrives at US-East at T+150ms. What is the probability the token is available at US-East by T+150ms? Assuming a log-normal distribution with P50=50ms and P99.9=300ms, approximately where is T+150ms in the distribution?
- Follow-up: The globally-consistent key-value store has a 45-second outage due to a network partition. During this outage, your credential freshness tokens are unavailable. Authentication requests that involve a recent password change (within the last 5 minutes) cannot verify freshness. You have two fallback options: (a) deny all auth requests that cannot verify freshness — safe but causes user lockouts; (b) fall back to eventual consistency — allow auth based on whichever replica is available, accepting the risk of a stale-hash acceptance. Design the fallback decision rule: under what conditions does option (a) apply vs. option (b)? At what point does the risk of option (b) — a user authenticating with an old password — become unacceptable?

> *Discussion notes:*
> - *Runbook entry: classify as expected behavior if the auth failure duration is within the configured P99 cross-region lag (800ms). Classify as system malfunction if the auth failure persists beyond 2x P99 lag (1,600ms). Page the on-call engineer if failures persist beyond 5 seconds.*
> - *Credential freshness token mechanism: on password change, write to global store: key = user_id, value = {hash: new_password_hash, timestamp: T, ttl: 300s}. On every auth request, US-East checks the global store for a token for this user_id. If token exists and age < 300s, use the token's hash instead of the local replica's hash.*
> - *Latency impact: 50ms P50 global store lookup per auth for users who changed their password in the last 5 minutes. Cache miss (no token, or token expired) returns in under 10ms. Fraction of users with an active token: assuming 1 password change per user per 6 months, and a 5-minute token TTL: 5min / (6 months x 43,200 min/month) = 0.002% of users at any moment. Overhead is negligible.*
> - *45-second outage fallback decision: option (b) — fall back to eventual consistency — is acceptable if fewer than 0.01% of users are simultaneously in an active password-change window. The exploit requires: user changed password AND attacker sends auth with old password AND the credential store is down. All three conditions simultaneously. For most applications, this probability is below the risk threshold. Accept option (b) and log the fallback events.*

---

---

## How to Use These Questions

Work through Section A questions before Section B. Section A questions are self-contained — they can be answered using only the material in Chapter 20. Section B questions require you to hold two chapters in mind simultaneously. If you find yourself unsure how a cross-chapter question connects to the second chapter, go back and re-read the relevant section of that chapter before attempting the question again.

Strong answers to these questions share three properties: they state a specific model or mechanism (not just "use strong consistency"), they give a specific number (latency in ms, cost in dollars, probability in percent), and they name the failure mode for the approach they recommend.

The cross-chapter questions in Section B are intentionally harder than anything in the original Q1-Q30 set. They are the type of question an interviewer asks at the 35-40 minute mark of a 45-minute session, after the candidate has already demonstrated baseline competence. These questions are not designed to have a single correct answer — they are designed to surface how you reason under uncertainty. Focus on the structure of your reasoning, not on finding the "right" answer.

---


### Cross-chapter from Ch21: Sharding Under GDPR Data Residency

**Question 44 — Ch21 + Ch36: Sharding Under GDPR Data Residency**

Your user database is sharded by user_id hash across 8 shards, all in US-East. You have 20 million users: 14 million in North America, 4 million in the EU, 2 million in APAC. GDPR Article 44 prohibits transferring EU personal data outside the EU without adequate safeguards. Your current architecture stores EU user data on US servers, in violation of GDPR.

- What is the specific GDPR violation in your current architecture? What is the legal risk classification — is this an Article 83(4) violation (up to 2% of global annual turnover) or an Article 83(5) violation (up to 4%)? What is the maximum fine exposure for a company with $500M annual revenue?
- Design the migration from user_id hash sharding to a sharding strategy that supports EU data residency. Your new strategy must guarantee that EU users' personal data is written to and read from EU-resident infrastructure only. Describe the new shard key or composite key strategy, the routing logic change, and the migration plan for the 4 million existing EU users.
- Your shard routing layer must enforce data residency as a hard constraint, not a soft preference. Design the enforcement mechanism: what prevents an application bug from routing an EU user's write to a US shard? This enforcement must be: machine-readable (not documentation), testable in CI, and auditable for compliance review.
- Follow-up: An EU user and a US user collaborate on a shared document. The document is owned by the EU user — all writes go to EU infrastructure. The US user makes frequent edits. Each edit requires a write to EU infrastructure, adding 90ms of cross-region latency to every US-user edit. This latency is user-perceptible during real-time collaboration. Design the architecture that reduces the US user's edit latency while maintaining GDPR compliance. What data can live in US-East without violating GDPR, and what must always remain in EU-West?

> *Discussion notes:*
> - *GDPR violation: Article 46 (cross-border transfer without adequate safeguards). Falls under Article 83(5) — up to 4% of global annual turnover. For a $500M revenue company: maximum fine $20M.*
> - *New shard key strategy: composite key (region_code, user_id_hash). EU users assigned region_code = 'eu' at registration, routed exclusively to EU-West shards. Existing EU users must be migrated: extract user_ids where country is in the EU, move their rows to EU-West shards.*
> - *Enforcement at the proxy layer: use PgBouncer or a custom TCP proxy as the database gateway. An ACL maps connection source (EU-West application tier) to EU-West shards only. US-East application tier cannot establish connections to EU-West shards. This enforcement is at the network layer — auditable via firewall logs.*
> - *Shared document collaboration — what can live where: document content and edit history are personal data (tied to the EU user's account) and must stay in EU-West. The US user's real-time edit operations (operational transforms, CRDTs) are mathematical deltas — they contain no personal data and can be processed in US-East.*
> - *Reduced-latency collaboration architecture: US user's browser sends edits to a US-East edge service. The edge service strips any user-identifying context and forwards only the transform delta (e.g., "insert character 'x' at position 47") to EU-West. EU-West applies the delta and returns a document version number. The acknowledgment to the US user is the version number — no personal data crosses from EU to US. User-perceptible latency: US-East edge acknowledgment in under 10ms, vs. full 90ms round-trip without the edge service.*

---


### Cross-chapter from Ch21: Multi-Region Shard Rebalance Under Compliance

**Question 48 — Ch21 + Ch36 + Ch20: Multi-Region Shard Rebalance Under Compliance**

Setup: sharded user database across two regions — US-East (shards 1-4) and EU-West (shards 5-8). US users are on shards 1-4, EU users on shards 5-8. Each region maintains a full DR copy (async cross-region replication, 150ms mean lag, 800ms P99). A GDPR audit flags that the US-East DR copy contains EU user data (shards 5-8) — this is technically a cross-border data transfer.

Simultaneously, shard 3 in US-East is at 92% disk capacity and needs to be split within 14 days.

- The GDPR remediation requires removing EU user data from US-East's DR copy. The capacity emergency requires splitting shard 3. If these run concurrently, identify the specific race condition that can corrupt data. Describe the sequence of events in the race condition precisely.
- Design the sequencing to prevent the race condition. Which operation must complete first, and what is the minimum safe gap between the completion of operation 1 and the start of operation 2? What is the go/no-go gate between the two operations?
- During the shard 3 split (24-hour migration window), every write to a shard 3 key goes to: (a) the existing shard 3 primary, (b) the new shard 9 primary (double-write), (c) the EU-West DR copy's shard 3, and after the GDPR fix, no longer to (d). Draw the write topology during the migration window. How many write acknowledgments does a write to a shard 3 key require before returning success to the client?
- Follow-up: The shard 3 split completes. The US-East routing table is updated to send certain user_ids to shard 9 instead of shard 3. The routing table update propagates to all US-East nodes in 30 seconds. During this 30-second propagation window, some US-East nodes still route to shard 3 for user_ids that should now go to shard 9. A user in this key range writes their profile during the propagation window. The write goes to shard 3 (old routing). The write is not on shard 9 (new routing). After propagation completes, the user reads their profile — the read goes to shard 9. They see the old profile. Describe the consistency model the user experienced during this 30-second window. Design the client-side retry logic that makes this failure transparent to the user.

> *Discussion notes:*
> - *Race condition: shard 3 split double-writes to shard 3 and shard 9. GDPR remediation simultaneously modifies EU-West DR replication topology. If DR replication is briefly interrupted during the topology change AND the shard 3 primary fails before replication resumes, writes from the double-write window are lost from EU-West's DR copy. Data loss window = interruption duration × write rate.*
> - *Correct sequencing: complete GDPR remediation first. Verify new DR topology is stable (< 200ms lag for US shards to EU-West) for 48 hours. Only then start the shard 3 split. Go/no-go gate: automated check that DR replication lag for all US shards is below 200ms for 48 consecutive hours.*
> - *Write topology during the 24-hour shard 3 split: each write to a shard 3 key goes to (1) shard 3 primary (synchronous, required for success), (2) shard 9 primary (asynchronous double-write), (3) EU-West DR copy of shard 3 (async, post-GDPR). The client receives success after shard 3 primary confirms. Shard 9 and DR are eventually consistent followers.*
> - *30-second routing table propagation window consistency model: the user experienced eventual consistency. Their write was acknowledged and durably stored on shard 3. But reads during the propagation window may route to shard 9 (incorrect shard for this user_id during the window) and not find the write.*
> - *Client-side retry logic: the write response includes the write's WAL LSN and the shard ID that accepted it. The next read request includes this in an X-Write-Token header. The routing layer checks: does the target shard have this LSN applied? If not (wrong shard or stale shard), escalate to the shard 3 primary directly. This is the read-your-writes mechanism applied to shard routing propagation.*

---

### Cross-chapter from Ch26: Per-feature CAP policy in multi-region active-active

**Question 37 -- Ch26 + Ch36: per-feature CAP policy in a multi-region active-active system**

An active-active multi-region system is inherently AP at the region level: if a network partition separates two regions, both continue serving (availability) but data diverges (consistency violated). The per-feature CAP policy determines which features you accept this trade-off for, and which you do not.

- For a social platform with global active-active deployment, define the CAP policy for each feature: (a) user login/authentication, (b) posting new content, (c) reading the feed, (d) payment processing, (e) push notification delivery. For each: can this feature tolerate serving from a partitioned (stale) region?
- For features you marked "must be CP": what is the user experience during a region-level partition? (They cannot perform that action.) How do you communicate this to the user? How long is acceptable unavailability?
- Follow-up: User authentication must be CP (you cannot let a revoked user log in from a stale replica). But this means during a regional partition, users in the affected region cannot log in. Design an alternative: a "read-only mode" where authenticated sessions continue to work (AP) but new logins are blocked (CP). What are the security implications of this design?


### Cross-chapter from Ch27: TrueTime and global linearizability in Spanner

**Question 40 -- Ch27 + Ch36: TrueTime and global linearizability in Spanner**

Google Spanner achieves external consistency (linearizability) globally across continents using TrueTime -- GPS-synchronized clocks with bounded uncertainty. Every timestamp in Spanner is a range [T_earliest, T_latest]. Before committing, Spanner waits until the uncertainty window passes (commit wait). This guarantees that any transaction committed after another is provably later, even across data centers.

- Why does NTP (millisecond accuracy, 1-100ms uncertainty) fail for global linearizability, while GPS (microsecond accuracy, ~7ms uncertainty) succeed? The commit wait must be longer than the clock uncertainty. With NTP at 100ms uncertainty: commit wait = 100ms per transaction. At 10K writes/second: this is acceptable. At 1M writes/second: not acceptable.
- CockroachDB uses HLC (not GPS) with maximum clock offset enforcement (500ms). How does CockroachDB achieve linearizability without TrueTime? (It reads timestamps from HLC and waits for the uncertainty window.) What is the latency overhead vs Spanner's GPS-based approach?
- Follow-up: You are designing a global financial ledger. TrueTime (Spanner) gives you global linearizability with 7-10ms commit latency overhead. HLC (CockroachDB) gives you similar guarantees with 2-5ms overhead but requires bounded clock skew enforcement. For a ledger processing 100K global transactions/second: which approach do you choose? What is the cost difference? (Spanner: Google Cloud cost. CockroachDB: self-hosted or managed cost.) Calculate the latency and cost trade-off.

---

## Exercises

**Exercise 1 — Active-active vs. active-passive.** For each system, choose active-active or active-passive and justify: (a) payment processing (global users, data consistency critical), (b) social media feed (global users, eventual consistency acceptable), (c) internal analytics dashboard (US only, used during business hours). What's the cost and complexity difference for each?

**Exercise 2 — Conflict resolution design.** You're building an active-active document editing system. Two users in different regions simultaneously edit the same document section. Design the conflict resolution strategy: last-write-wins (LWW), operational transforms (OT), or CRDTs. What's the user experience implication of each?

**Exercise 3 — Data residency compliance.** EU users' data must stay in the EU. US users' data must stay in the US. Design the routing and storage architecture. What happens when a US user travels to the EU and accesses their account? What's the edge case with shared data (a US-EU collaboration space)?

**Exercise 4 — Cross-region failover drill.** Design a failover runbook: primary region goes down at 2am. What automated recovery happens, what requires manual intervention, what's the expected RTO and RPO, and what's the validation step before declaring recovery complete?

**Exercise 5 — Replication lag impact.** Your active-passive setup has 200ms replication lag. A user creates an account in the primary region, then their mobile app (hitting the secondary) immediately reads their profile. Walk through: what do they see? How do you fix this? What's the trade-off of the fix?

**Exercise 6 — Traffic routing strategy.** Your service has three regions: US-East, EU-West, Asia-Pacific. You want to route each user to the closest region. Design: DNS-based routing, health check integration, what happens when a region is degraded (partial failure vs. complete), and how you avoid routing loops.

---

## Homework

**Assignment 1 — Region expansion plan.** Your service currently runs in one region. Write a multi-region expansion plan: which region to add first (and why), what must be replicated vs. what can stay regional, what new failure modes are introduced, and what's the runbook for a regional failover.

**Assignment 2 — Latency measurement.** Set up latency measurements between your service and users in 3 different geographic locations. Identify the slowest region. Propose whether a CDN, a new region, or an edge cache would fix the problem — and justify based on the latency breakdown.

**Assignment 3 — Interview practice: multi-region design.** Practice "design a globally consistent key-value store" in 45 minutes. Cover: consistency model choice, replication topology, conflict resolution, failover strategy, and how you handle the partition between regions during a network split.

**Assignment 4 — Read the Amazon Dynamo paper (DeCandia et al., 2007).** Write a one-paragraph summary: what trade-offs did Dynamo make (availability over consistency, eventual consistency, vector clocks), and why were those trade-offs the right choice for Amazon's use case at the time?

