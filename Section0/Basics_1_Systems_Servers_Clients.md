# Basics Chapter 1: Systems, Servers, Clients — The Foundation of Everything

---

# Introduction

Every distributed system—from a simple blog to Google's search infrastructure—rests on the same foundation: **systems** composed of **servers** and **clients** exchanging **requests** and **responses**. These concepts seem elementary. And yet, Staff-level system design interviews often reveal that candidates who can architect complex systems struggle to articulate how these fundamentals compose, where boundaries lie, and why each layer matters at scale.

This chapter grounds you in the foundation. We'll explore what a "system" really means when you're thinking beyond a single service, what distinguishes servers from clients (and why the same process can be both), what actually happens when you type a URL, and how the request/response pattern scales—and breaks—in production systems. By the end, you'll have the language and mental models to discuss these basics with Staff-level precision, connecting simple concepts to the trade-offs that define real-world architecture.

---

# Part 1: What is a "System" in Software?

## The Intuition: Many Parts, One Purpose

A **system** in software is a collection of components that work together to serve a purpose. Not one program. Not one server. Many pieces—each with a role—coordinating to achieve something none could achieve alone.

Think of a restaurant. The menu, the waiter, the kitchen, the fridge, the stove, the cash register—each does one thing. No single component can run the restaurant. Together, they create the experience. That's a system.

In software, when you open Netflix, you see movies. Behind that single experience: recommendation services, video delivery infrastructure, playback state storage, payment processing, authentication. None of these can deliver "watch a movie" alone. Together, they form a **system**.

## Components That Make Up Systems

Software systems typically include some combination of:

| Component | Role | Example |
|-----------|------|---------|
| **Servers** | Process requests, run business logic | Web servers, API services, microservices |
| **Databases** | Persistent storage, source of truth | PostgreSQL, DynamoDB, Cassandra |
| **Caches** | Fast read access, reduce load on primary stores | Redis, Memcached, CDN |
| **Queues** | Async processing, decoupling producers/consumers | Kafka, RabbitMQ, SQS |
| **Load balancers** | Distribute traffic across servers | nginx, HAProxy, cloud LBs |
| **Clients** | Initiate requests (browsers, apps, other services) | Browser, mobile app, service-to-service caller |

A system isn't defined by a single component. It's defined by the **collection** and how they **interact**.

## System Boundaries: Where Does "Your System" End?

This question matters deeply at Staff level. If you're designing a notification system, does "your system" include:
- The email delivery provider (SendGrid, AWS SES)?
- The mobile push infrastructure (FCM, APNs)?
- The user preference service that decides who gets what?
- The analytics pipeline that tracks delivery?

**The answer affects everything**: ownership, failure modes, SLAs, capacity planning, and debugging. Staff engineers explicitly define boundaries and document what's inside vs. outside.

### Why This Matters at Scale

At small scale, "the system" might be "our monolith and our database." At Staff level, you're often designing or owning systems where:
- Third-party services are in the critical path (payment providers, CDNs)
- Multiple teams own different components
- A single user request crosses 5–10 internal services and 2–3 external ones

If you don't define boundaries, you can't assign ownership, measure health, or contain failures. "System thinking" means asking: *What's in scope? What's a dependency? Who owns what?*

## System vs. Service vs. Application — Distinctions That Matter

| Term | Scope | Example |
|------|-------|---------|
| **Application** | A deployable unit that users interact with | "The Netflix iOS app" |
| **Service** | A single logical component exposing an interface | "The recommendation service," "the auth service" |
| **System** | The full set of components delivering a capability | "The Netflix streaming system" (CDN, transcoding, playback, billing) |

**Why the distinction matters**: In interviews and in practice, you'll hear "design a system" when the scope might span many services. You'll hear "implement a service" when the scope is one component. Staff engineers clarify: "When you say 'design a rate limiter,' are we designing the rate limiter *service*, or the *system* that includes the gateway, storage, and configuration?"

## Why "System Thinking" is the Core Staff Engineer Skill

L5 engineers often think in components: "I'll build the rate limiter. I'll make it fast." L6 engineers think in systems: "The rate limiter will sit in front of 12 services. If it goes down, we fail open or closed? What's the blast radius? How does configuration propagate? Who operates it?"

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SYSTEM THINKING: L5 vs L6                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   L5: "I built the cache layer"                                         │
│   L6: "The cache layer reduces DB load by 60%, but if it fails we       │
│        have thundering herd—here's our stampede protection"            │
│                                                                         │
│   L5: "Our service handles 10K QPS"                                      │
│   L6: "Our service handles 10K QPS, but each request fans out to       │
│        3 downstream services—we're responsible for 30K downstream QPS"│
│                                                                         │
│   L5: "The database is the bottleneck"                                  │
│   L6: "The database is the bottleneck; here's the read/write ratio,    │
│        why replication lag matters, and the migration path to shard"   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Staff-Level Insight**: The jump from "I own this component" to "I understand how this component affects the whole system" is the essence of Staff-level thinking. When you design, you're not just building a thing—you're defining how it fits into a larger whole, what it depends on, what depends on it, and what happens when it fails.

### Why This Matters at Scale

At 10 services, you can maybe keep the full picture in your head. At 100 services, you need explicit boundaries, dependency graphs, and ownership. At 1000, you need platforms that enforce boundaries (service mesh, API gateways) and observability that traces requests across them. System thinking scales only when it's codified—in documentation, in tooling, and in the decisions you make about where to draw lines.

## ASCII Diagram: Simple vs. Complex System

**Simple system** (client → server → database):

```
    ┌──────────┐         ┌──────────┐         ┌──────────┐
    │  CLIENT  │ ──────► │  SERVER  │ ──────► │ DATABASE │
    │ (Browser)│         │  (API)   │         │  (e.g.   │
    │          │ ◄────── │          │ ◄────── │ Postgres)│
    └──────────┘         └──────────┘         └──────────┘
         │                     │                     │
         │   HTTP Request      │   SQL Query          │
         │   HTTP Response     │   Query Result       │
         └─────────────────────┴─────────────────────┘
         
    One request path. One hop to server. One hop to DB.
    Latency: client → server → DB → server → client.
```

**Complex system** (multiple services, caches, queues, load balancer):

```
    ┌──────────┐     ┌─────────────┐     ┌──────────────┐
    │  CLIENT  │────►│ Load Balancer│────►│ API Gateway   │
    └──────────┘     └──────┬───────┘     └──────┬───────┘
                           │                     │
              ┌────────────┼────────────┐        │
              │            │            │        │
              ▼            ▼            ▼        ▼
         ┌─────────┐  ┌─────────┐  ┌─────────┐ ┌─────────────┐
         │Service A│  │Service B│  │Service C│  │   Cache     │
         │ (Auth)  │  │(Profile)│  │ (Feed)  │  │  (Redis)    │
         └────┬────┘  └────┬────┘  └────┬────┘  └──────┬──────┘
              │            │            │               │
              └────────────┼────────────┘               │
                           │                           │
                           ▼                           │
                    ┌─────────────┐                    │
                    │   Queue     │◄───────────────────┘
                    │  (Kafka)    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌─────────┐  ┌─────────┐  ┌─────────┐
         │   DB    │  │   DB    │  │ Worker   │
         │Primary  │  │ Replica │  │ Service  │
         └─────────┘  └─────────┘  └─────────┘
         
    One user request → many service calls, cache lookups, queue publishes.
    Latency = sum of all hops; failure can occur at any layer.
```

### L5 vs L6: System Boundaries

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Scope** | "I'm building the auth service" | "The auth service is a dependency for 8 services; its failure affects X, Y, Z" |
| **Boundaries** | Implicit, assumed | Explicit, documented, owned |
| **Dependencies** | "We call Stripe for payments" | "Stripe is in our critical path; we need circuit breakers, fallbacks, and a status page" |
| **Failure** | "Our service is resilient" | "If our service fails, these 3 systems degrade; here's the containment strategy" |

## System Boundaries in Practice

Where you draw the line between "our system" and "external" is one of the most consequential decisions in system design. In practice, companies draw boundaries differently depending on ownership, risk tolerance, and operational reality.

### Real-World Examples: Where Companies Draw Boundaries

**E-commerce checkout system**: At many companies, "the checkout system" includes:
- *Inside the boundary*: Cart service, inventory service, order service, payment orchestration service, checkout UI
- *Outside the boundary*: Stripe (payment processor), Twilio (SMS for OTP), SendGrid (order confirmation email), CDN (static assets)

Why? The team owns the orchestration logic. They do NOT own payment rails, SMS delivery, or email delivery. Those are vendor responsibilities. The boundary is drawn at the *integration point*: our service calls Stripe's API; what happens inside Stripe is not our system.

**Notification system**: A notification platform might define its boundary as:
- *Inside*: Notification preference service, routing logic, templating, delivery queue, retry logic, analytics
- *Outside*: FCM (Firebase Cloud Messaging), APNs (Apple Push Notification service), SendGrid, Slack API

The system "owns" *deciding what to send and when*. It does not own *delivering bytes to the device*. That distinction matters for SLAs: "We guarantee 99.9% delivery to our queue" vs. "We guarantee 99.9% delivery to the user's phone"—the latter would require owning FCM/APNs, which is impossible.

**When external services are *inside* the boundary**: Some companies treat critical vendors as *part of* the system for capacity and incident purposes. Example: A fintech might say "our payment system = our orchestration + Stripe" because a Stripe outage is indistinguishable from "payments are down" to users. The *operational* boundary includes Stripe; the *engineering* boundary does not.

### How Boundaries Affect Blast Radius

**Blast radius** = how much of the system fails when component X fails.

If "our system" = API + 5 services + DB, and the DB fails → blast radius = 100% (everything fails).

If "our system" = API + 5 services + DB + "and we call Stripe," then:
- DB failure → our system fails
- Stripe failure → our *payment flow* fails, but cart, browse, account still work

Drawing the boundary *narrower* (excluding Stripe) means: "When Stripe is down, *our* system status is green—Stripe is an external dependency." Drawing it *wider* means: "We report payment success as part of our SLA; Stripe downtime is our downtime for that capability."

**Staff-level decision**: You define blast radius by defining boundaries. A smaller boundary = smaller blast radius for *your* team's ownership, but users may not care—they see "checkout is broken." Document both: *technical* boundary (what we operate) and *user-facing* boundary (what capabilities we're accountable for).

### How Boundaries Affect Ownership and SLAs

| Boundary Choice | Ownership | SLA Implication |
|-----------------|-----------|------------------|
| External service *outside* boundary | "We integrate; they operate" | Our SLA: "We deliver requests to their API in X ms." We do NOT promise their uptime. |
| External service *inside* boundary | "We're accountable for end-to-end" | Our SLA includes their failure modes. We need fallbacks, status page integration, runbooks. |
| Multi-team system | "Team A owns service X; Team B owns Y" | SLA is the *intersection* of component SLAs. 99.9% × 99.9% = 99.8% combined. |

**Example**: "Our API has 99.95% uptime" is meaningless if the API calls a down payment provider 5% of the time. The *user-facing* SLA for "complete a purchase" may be lower. Staff engineers make this explicit: "Our API uptime is 99.95%. End-to-end purchase success depends on Stripe; we measure and report that separately."

### A Staff Engineer Defines Boundaries; A Senior Engineer Works Within Them

- **Senior Engineer (L5)**: "I'll build the notification service. It will call SendGrid and FCM." They implement within the boundaries they're given. They may not question whether SendGrid should be in or out.

- **Staff Engineer (L6)**: "Before we build, let's define the boundary. Are we owning delivery SLAs or just routing? If SendGrid is down, do we fail the whole notification or queue for retry? Who's on the hook when a partner is slow?" They *define* the boundary, document it, and ensure the team and stakeholders agree.

In interviews, demonstrating boundary-thinking means: "I'd start by defining what's in scope. Our system will include X, Y, Z. We'll treat A, B as external dependencies with documented fallbacks. Here's how that affects our SLAs and failure modes."

---

# Part 2: What is a Server? What is a Client?

## Server: A Process Listening on a Port

A **server** is a process that listens on a network port, waiting for requests. It doesn't initiate—it **responds**. When a request arrives, it processes it and sends a response.

Technically: a server binds to a port (e.g., 80 for HTTP, 443 for HTTPS) and blocks, waiting for incoming connections. When a client connects and sends data, the server parses the request, does work (query DB, run logic, call other services), and sends back a response.

## Client: Anything That Makes a Request

A **client** is anything that initiates a request. It could be:
- A **browser** (user types URL, clicks a link)
- A **mobile app** (user taps "load feed")
- **Another service** (Service A calls Service B to get user data)
- A **curl command** or script
- A **cron job** or batch process

The client doesn't wait passively. It **asks**. The server **answers**.

## The Same Process Can Be BOTH Client and Server

This is crucial. Service A might be a **server** to the mobile app (it receives HTTP requests) and a **client** to the database (it sends queries) and a **client** to Service B (it makes RPC/HTTP calls). Roles are **per-request**, not per-process.

```
    ┌─────────────┐
    │ Mobile App  │  ← CLIENT (to API)
    │  (Client)   │
    └──────┬──────┘
           │ HTTP request
           ▼
    ┌─────────────┐
    │  API Server │  ← SERVER (to app) AND CLIENT (to DB, Service B)
    │ (Both!)     │
    └──────┬──────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌─────────┐
│Database │  │Service B │
│(Server) │  │(Server)  │
└─────────┘  └─────────┘
```

At Staff level, you trace the full chain: "This user request hits our API. Our API is a client to the user service, the feed service, and the database. Each of those might be a client to something else." Understanding this chain is how you debug latency, assign ownership, and reason about failure propagation.

## Physical Server vs. Virtual Server vs. Container vs. Serverless

The term "server" is overloaded:

| Term | What It Really Is | Use Case |
|------|-------------------|----------|
| **Physical server** | Bare metal: CPU, RAM, disk, network | High performance, legacy, specialized workloads |
| **Virtual machine (VM)** | OS running on hypervisor, shares physical hardware | Traditional cloud workloads, full OS control |
| **Container** | Process isolation with shared kernel (e.g., Docker) | Microservices, consistent dev/prod, density |
| **Serverless function** | Ephemeral process, invoked on event/request | Event-driven, variable load, pay-per-use |

**Evolution**: Early systems ran one process per physical server. Virtualization let one machine host many VMs. Containers increased density and portability. Serverless removed the "always-on" server—you pay for execution, not idle time.

**Staff-level implication**: When you design a system, the deployment unit (VM, container, function) affects cold starts, scaling granularity, and cost. A serverless function may have 100ms+ cold start; a long-running container doesn't. Choose based on latency and traffic patterns.

## Server Evolution Deep Dive

The journey from bare metal to serverless represents decades of innovation in resource utilization, isolation, and operational flexibility. Understanding each stage—and why the industry moved through them—helps you make informed deployment choices.

### Bare Metal → VMs → Containers → Serverless: The Progression

**Bare metal (pre-2000s)**: One physical machine ran one application. To scale, you bought more machines. Provisioning took days or weeks. Utilization was often 5–15%—servers sat idle most of the time. But you had full control: no hypervisor overhead, predictable performance, no noisy neighbors.

**Virtual machines (mid-2000s onward)**: Hypervisors (VMware, Xen, KVM) let one physical host run many VMs. Each VM had its own OS, kernel, and isolation. Multi-tenancy became possible: one datacenter served many customers. Utilization improved to 50–70%. Trade-off: each VM carried a full OS (GBs of RAM, minutes to boot). Overhead: ~2–5% CPU, significant memory for the hypervisor.

**Containers (2013 onward, Docker)**: Containers share the host kernel. No separate OS per container—just isolated processes with their own filesystem, network, and cgroups. Startup: seconds, not minutes. Density: 10–50 containers per VM, or more. Overhead: ~1–3% CPU, minimal memory. *Containers won* because they offered isolation *and* efficiency—close to bare-metal performance with VM-like multi-tenancy.

**Serverless (2014 onward, Lambda, etc.)**: No always-on server. You deploy *functions*; the platform invokes them on events. Billing is per-invocation and per-duration. Zero idle cost. Auto-scaling is built-in. Trade-off: cold starts (100ms–10s depending on runtime and size), vendor lock-in, and debugging complexity.

### Resource Overhead Comparison

| Deployment | CPU Overhead | Memory Overhead | Boot/Cold Start | Density (per host) |
|------------|--------------|-----------------|-----------------|---------------------|
| **Bare metal** | 0% | 0% | N/A (always on) | 1 app |
| **VM** | 2–5% | 1–4 GB (hypervisor + guest OS) | 1–5 min | 5–20 VMs |
| **Container** | 1–3% | 10–50 MB (per container) | 1–10 sec | 50–200+ containers |
| **Serverless** | Managed by vendor | Managed; ~128 MB–10 GB per function | 100 ms–10 s (cold) | N/A (vendor-managed) |

### Why Containers Won: Isolation + Efficiency

Containers offered a sweet spot:

1. **Isolation**: Each container has its own filesystem, network namespace, process tree. A bug or crash in one doesn't take down others. Resource limits (CPU, memory) via cgroups prevent noisy neighbors.

2. **Efficiency**: Shared kernel means no redundant OS per workload. A VM might need 2 GB for the OS; a container adds tens of MB. You could run 10× more workloads on the same hardware.

3. **Portability**: "It works on my machine" became "it works in this image." Docker images run identically from dev to staging to production. No "works on Ubuntu 18, fails on RHEL 7" surprises.

4. **Fast startup**: Restart a crashed service in seconds. Scale up new replicas quickly. Critical for elastic systems.

### Docker vs. Kubernetes

- **Docker**: Container runtime + image format + CLI. You run `docker run` and get a container. Good for single-node, dev, small deployments.

- **Kubernetes**: Orchestration layer *on top of* container runtimes (containerd, CRI-O). Handles scheduling, scaling, self-healing, networking, storage. You declare "I want 10 replicas of this service"; Kubernetes places them, restarts failed pods, balances load.

**When to use what**:
- **Docker alone**: Single server, small team, simple deployments.
- **Kubernetes**: Multi-node, microservices, need rolling updates, auto-scaling, service discovery. Kubernetes is complex—only use it when you need orchestration.

### Serverless Trade-offs

| Trade-off | Implication |
|-----------|-------------|
| **Cold start** | First request after idle period incurs 100ms–10s delay. Mitigation: keep-warm pings, provisioned concurrency (paid), or accept latency for non-critical paths. |
| **Vendor lock-in** | Lambda, Cloud Functions—each has its own APIs, limits, quirks. Porting between clouds is non-trivial. Consider serverless frameworks (Serverless Framework, SST) that abstract some differences. |
| **Debugging difficulty** | No SSH. Logs and traces are your tools. Distributed tracing (X-Ray, Jaeger) becomes essential. Reproducing production locally is harder. |
| **Timeout limits** | Lambda: 15 min max. Long-running jobs need step functions, queues, or a different compute model. |
| **Local state** | Ephemeral—no local disk that persists. Everything in S3, DynamoDB, or external store. |
| **Cost model** | Pay per invocation and GB-second. Cheap at low/medium volume; can get expensive at very high QPS (millions/day). Compare to always-on container cost. |

### When Each Is Appropriate

| Use Case | Recommended | Rationale |
|----------|-------------|-----------|
| **High-performance, predictable load** | Bare metal or VM | Latency-sensitive, need full control (e.g., trading systems, gaming servers). |
| **Microservices, elastic scaling** | Containers (K8s) | Industry standard. Portable, scalable, good tooling. |
| **Event-driven, sporadic traffic** | Serverless | Webhooks, async processing, cron jobs. No idle cost. |
| **Startup, small team** | Managed containers (ECS, Cloud Run) or serverless | Less ops burden than raw K8s. |
| **Legacy monolith** | VM | Often easier to lift-and-shift a VM than to containerize. |

**Staff-level decision**: Choose based on traffic pattern, latency requirements, team size, and operational maturity. "We use Kubernetes because we have 50 services and need orchestration" is valid. "We use Lambda for webhooks because they're sporadic and we don't want to pay for idle servers" is also valid. The wrong choice: "We use serverless for our user-facing API" when p99 latency matters and cold starts would hurt.

## Server Capacity: What Limits a Single Server?

A single server is limited by:

| Resource | Typical Limits (rough) | What It Affects |
|----------|------------------------|-----------------|
| **CPU** | Cores (e.g., 4–64) | Compute-bound work: encryption, compression, complex logic |
| **Memory (RAM)** | GB (e.g., 8–256 GB) | In-memory caching, connection state, large datasets |
| **Disk I/O** | IOPS, throughput | Database, file storage, logging |
| **Network** | Bandwidth, connections | Serving responses, calling other services |

**Bottleneck varies by workload**: A stateless API might be CPU-bound. A cache might be memory-bound. A database might be disk I/O bound. Staff engineers profile first, then optimize.

## How Many Requests Can One Server Handle?

Rough numbers (highly workload-dependent):

| Workload | Approx. QPS per server (single core) | Notes |
|----------|--------------------------------------|------|
| **Static file** | 10,000–100,000+ | nginx serving files from memory |
| **Simple API** | 1,000–10,000 | Stateless, minimal logic, cached |
| **API + DB query** | 100–1,000 | Per-request DB round-trip |
| **Heavy computation** | 10–100 | Encryption, ML inference |
| **WebSocket** | 1,000–10,000 connections | Depends on message rate |

**Why this matters for capacity estimation**: If you need to serve 100K QPS of simple API calls, you might need ~10–100 servers (depending on actual workload). If each request does 3 DB queries and 2 external API calls, the number changes dramatically. Staff engineers do back-of-envelope math: QPS × latency = concurrent requests; concurrent requests / (QPS per server) = server count.

### Why This Matters at Scale

Capacity planning starts at the single-server level. You can't scale out effectively if you don't know:
- What one server can handle
- What the bottleneck is (CPU, memory, I/O, network)
- How adding more servers changes the equation (linear vs. sublinear due to shared resources)

**Staff-Level Insight**: "One server can handle X QPS" is a starting point, not a constant. It depends on request size, response size, caching, connection pooling, and the shape of your traffic. Staff engineers build a mental model: "For our typical request mix, one node handles ~2K QPS. At 50K QPS we need ~30 nodes for headroom."

## ASCII Diagram: One Server Serving Many Clients

```
                    ┌─────────┐
                    │ Client 1│
                    └────┬────┘
                         │
                    ┌─────────┐
    ┌─────────┐     │ Client 2│
    │ Client 3│     └────┬────┘
    └────┬────┘          │
         │               │      ┌─────────────────┐
         │          ┌────┴───────│     SERVER      │
         └──────────│           │  (one process,   │
                    │           │   many clients)  │
    ┌─────────┐     │           └────────┬────────┘
    │ Client 4│─────┘                    │
    └─────────┘                          │
                                         ▼
                                 ┌───────────────┐
                                 │   Database    │
                                 │ (Server is    │
                                 │  client here) │
                                 └───────────────┘
```

---

# Part 3: What Happens When You Type a URL?

Understanding the full request path—from keystroke to rendered page—is essential for debugging, latency optimization, and failure analysis. Staff engineers can trace a request through every hop and identify where time is spent and where failures can occur.

## The Full Journey (Step by Step)

### Step 1: DNS Resolution (~20–120 ms, often cached)

You type `https://www.example.com`. Your computer doesn't know where `www.example.com` lives. It asks the **DNS (Domain Name System)**.

Flow:
1. **Browser cache**: Browser may have cached the result from a previous visit. Hit: ~0 ms.
2. **OS cache**: OS resolver cache (e.g., `/etc/hosts`, systemd-resolved). Hit: ~0–1 ms.
3. **Stub resolver**: Query to configured resolver (e.g., ISP DNS, 8.8.8.8, 1.1.1.1). Resolver may have cached record.
4. **Recursive resolution** (if cache miss): Resolver queries root servers → TLD servers (.com) → authoritative nameservers (example.com). Each hop adds latency.
5. **Response**: Returns IP address (e.g., `93.184.216.34`) and caches it per TTL (Time To Live).

**Latency breakdown**: Local cache = 0 ms. Same-data-center resolver = 1–5 ms. Cross-region = 20–50 ms. Cold recursive resolution = 50–200 ms. Staff engineers running global services often use **GeoDNS** or **Anycast** so resolvers get answers from nearby PoPs.

**Where it can go wrong**: DNS hijacking (malicious redirect), slow/congested resolvers, misconfigured records, TTL expiry causing thundering herd (all clients re-resolve at once), DDoS on authoritative servers.

### Step 2: TCP Connection (~1–3 × RTT)

With the IP, the browser opens a **TCP connection** to the server (typically port 443 for HTTPS).

- **TCP handshake**: SYN → SYN-ACK → ACK. One RTT.
- **TLS handshake** (if HTTPS): ClientHello → ServerHello, certificate, key exchange. ~1–2 RTT.
- **Total**: ~2–3 RTT before first byte of application data.

**Typical RTT**: 20–100 ms locally; 50–200 ms cross-region; 200–400 ms intercontinental.

### Step 3: TLS Handshake (part of Step 2)

For HTTPS, after TCP is established:
- Negotiate cipher suite
- Server sends certificate
- Key exchange (e.g., ECDHE)
- Application data encrypted

**Where it can go wrong**: Invalid cert, expired cert, slow handshake (large cert chain, slow OCSP).

### Step 4: HTTP Request

Browser sends HTTP request, e.g.:

```
GET /home HTTP/1.1
Host: www.example.com
Accept: text/html, application/json
Cookie: session_id=xyz
```

Headers, body (if POST/PUT). Over the encrypted channel.

### Step 5: Server Processing

Server receives request. Depending on architecture:
- **Reverse proxy** (nginx, etc.): may serve static file or forward
- **Load balancer**: forwards to one of N backend servers
- **Application server**: runs business logic, queries DB, calls other services
- **CDN**: if cached at edge, response comes from nearby PoP

**Latency sources**: DB queries (1–100 ms per query, depending on index usage and data size), external API calls (50–500 ms for third-party services), cache misses (trigger DB or upstream calls), CPU-bound work (encryption, serialization, business logic). A single request might do 3 DB queries and 2 external API calls—latency adds up. Staff engineers profile the critical path and optimize the slowest operations first.

### Step 6: HTTP Response

Server sends response:

```
HTTP/1.1 200 OK
Content-Type: text/html
Content-Length: 1234

<html>...</html>
```

Status, headers, body. May be chunked for streaming.

### Step 7: Rendering

Browser receives response, parses HTML, discovers additional resources (CSS, JS, images), makes more requests. Each may trigger more DNS, TCP, TLS, request/response cycles. **Critical path** and **render-blocking resources** determine when the page becomes interactive.

**Practical detail**: A modern single-page app might load an HTML shell (small), then a JavaScript bundle (200 KB–2 MB), then make API calls for data. The user sees a loading spinner until JS parses, executes, fetches data, and renders. SSR reduces this by sending pre-rendered HTML so the user sees content before JS runs. **Critical path** = the chain of dependencies that must complete before the page is useful. Optimizing the critical path—e.g., inline critical CSS, defer non-essential JS—is a core frontend performance technique.

## Latency Budget (Typical)

| Step | Typical Latency |
|------|-----------------|
| DNS | 0 (cached) to 100 ms |
| TCP + TLS | 50–150 ms (1–2 RTT) |
| HTTP request/response | 10–500 ms (server-dependent) |
| Parsing + rendering | 50–200 ms |
| **Total (first paint)** | **100–1000 ms** |

**Staff-level implication**: To hit a 200 ms p99, you have little room. DNS and TCP+TLS alone can consume 100–150 ms. CDNs and connection reuse (HTTP/2, keep-alive) are essential.

## Where CDN, Load Balancer, Reverse Proxy Fit

```
    User's Browser
         │
         ▼
    ┌─────────┐
    │   DNS   │  → May return CDN IP (e.g., CloudFront) instead of origin
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │   CDN   │  → Edge cache; if HIT, response from nearby PoP (low latency)
    │  (Edge) │  → if MISS, request goes to origin
    └────┬────┘
         │
         ▼
    ┌─────────────────┐
    │ Load Balancer   │  → Distributes across origin servers
    └────┬────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Reverse Proxy  │  → Terminates TLS, routing, maybe static files
    │  (e.g. nginx)   │
    └────┬────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Application     │
    │ Servers         │
    └─────────────────┘
```

- **CDN**: Caches static (and sometimes dynamic) content at the edge. Reduces origin load and latency for cache hits.
- **Load balancer**: Spreads traffic across N servers. Health checks, failover.
- **Reverse proxy**: Sits in front of app servers, handles TLS, routing, compression.

## The Full URL Request Path — Deep Dive

When you type `https://www.example.com/page` and press Enter, the request traverses a long chain of systems before a single byte of response returns. Staff engineers can name every hop, estimate latency at each, and identify where optimization and failure handling matter most.

### Every Hop: From Keystroke to Response

The following diagram shows the *complete* path for a cache miss (CDN miss, request goes to origin). Each hop adds latency; each is a potential point of failure.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    FULL URL REQUEST PATH — EVERY HOP                                 │
│                    (Latency estimates: typical, not worst-case)                      │
└─────────────────────────────────────────────────────────────────────────────────────┘

    USER TYPES URL
         │
         │  HOP 1: Browser DNS Cache
         ▼  ┌─────────────────────┐
    ┌──────┴──┐  Check: Do we have  │  HIT: 0 ms | MISS: continue
    │ Browser │  example.com IP?   │
    │  Cache  │└─────────────────────┘
    └────┬────┘
         │  HOP 2: OS DNS Cache (e.g., systemd-resolved, /etc/hosts)
         ▼  ┌─────────────────────┐
    ┌──────┴──┐  OS-level cache    │  HIT: 0–1 ms | MISS: continue
    │   OS    │└─────────────────────┘
    │  Cache  │
    └────┬────┘
         │  HOP 3: Recursive Resolver (e.g., 8.8.8.8, ISP DNS)
         ▼  ┌─────────────────────┐
    ┌──────┴──┐  Resolver cache?   │  HIT: 1–5 ms | MISS: recursive resolution
    │Resolver │└─────────────────────┘
    └────┬────┘
         │  HOP 4: Root Nameserver (.)
         │  "Who knows .com?"  →  ~1–5 ms (cached heavily)
         │  HOP 5: TLD Nameserver (.com)
         │  "Who knows example.com?"  →  ~1–5 ms
         │  HOP 6: Authoritative Nameserver (example.com)
         │  "What's the IP for www.example.com?"  →  ~5–20 ms
         ▼  DNS TOTAL (cold): ~20–120 ms | (cached): 0–5 ms
    ┌────────────┐
    │  Got IP    │
    └─────┬──────┘
          │
          │  HOP 7: TCP Handshake (SYN → SYN-ACK → ACK)
          │  ~1 RTT  →  20–100 ms (local) to 200–400 ms (global)
          │
          │  HOP 8: TLS Handshake (see TLS 1.3 detail below)
          │  TLS 1.3: 1-RTT (same as TCP, ~1 RTT) | TLS 1.2: 2-RTT
          │  ~50–150 ms typical
          │
          ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  HOP 9: CDN Check (if using CloudFront, Cloudflare, etc.)               │
    │  DNS may return CDN IP. Request hits edge PoP.                           │
    │  Cache lookup: 1–5 ms.  HIT → return (skip origin). MISS → continue.    │
    └─────────────────────────────────┬───────────────────────────────────────┘
                                      │  MISS: request forwarded to origin
          │                           ▼
          │                  ┌─────────────────┐
          │                  │ HOP 10: Load Balancer  │  ~1–3 ms
          │                  │ Health check, pick backend                      │
          │                  └────────┬────────┘
          │                           │
          │                           ▼
          │                  ┌─────────────────┐
          │                  │ HOP 11: Reverse Proxy (nginx, etc.)  │  ~1–2 ms
          │                  │ TLS term, routing, maybe static     │
          │                  └────────┬────────┘
          │                           │
          │                           ▼
          │                  ┌─────────────────┐
          │                  │ HOP 12: Application Server  │  ~10–500 ms
          │                  │ Business logic, cache lookups, etc. │
          │                  └────────┬────────┘
          │                           │
          │                           ▼
          │                  ┌─────────────────┐
          │                  │ HOP 13: Connection Pool  │  Wait for conn: 0–5 ms
          │                  │ Checkout DB connection   │
          │                  └────────┬────────┘
          │                           │
          │                           ▼
          │                  ┌─────────────────┐
          │                  │ HOP 14: Database  │  ~1–100 ms per query
          │                  │ Query execution  │
          │                  └─────────────────┘
          │
          │  Response traverses back: DB → App → Reverse Proxy → LB → CDN → TLS → User
          │  Each hop adds ~0.5–5 ms typically
          │
          ▼
    [User sees response]
    
    TOTAL LATENCY (cache miss, cross-region):
    DNS: 20–50 ms + TCP: 50 ms + TLS: 50 ms + CDN: 5 ms + LB: 2 ms + Proxy: 2 ms
    + App: 50–200 ms + DB: 10–50 ms ≈ 200–400 ms+ typical
```

### TLS 1.3 Handshake: 1-RTT vs 2-RTT

**TLS 1.2 (legacy)**: Full handshake required 2 round trips:
1. ClientHello → ServerHello, Certificate, ServerKeyExchange, ServerHelloDone
2. ClientKeyExchange, ChangeCipherSpec, Finished
3. Application data could flow only after the second RTT.

**TLS 1.3 (modern)**: Optimized to 1 RTT for full handshake:
1. Client sends ClientHello with key share (ephemeral public key).
2. Server responds with ServerHello, certificate, key share, Finished—and can send application data in the same flight.
3. Client sends Finished. Application data can flow immediately after.

**Resumption (0-RTT)**: If the client has a session ticket from a previous connection, TLS 1.3 allows sending application data in the *first* flight (0-RTT). Risk: replay attacks—0-RTT data can be replayed. Use only for idempotent or safe operations.

| Scenario | RTTs | Typical Latency |
|---------|------|------------------|
| TLS 1.2 full handshake | 2 | 100–200 ms (cross-region) |
| TLS 1.3 full handshake | 1 | 50–100 ms |
| TLS 1.3 resumption (0-RTT) | 0 | 0 ms for handshake |

**Staff-level implication**: Enabling TLS 1.3 reduces connection establishment latency by ~50%. For connection reuse (HTTP/2, keep-alive), the handshake happens once per connection—subsequent requests on the same connection skip it. Cold connections (new user, new tab, expired connection) pay the handshake cost.

### Latency Estimates at Each Hop (Reference)

| Hop | Component | Typical Latency (Cached/Hit) | Typical Latency (Cold/Miss) |
|-----|-----------|------------------------------|-----------------------------|
| 1 | Browser DNS cache | 0 ms | — |
| 2 | OS DNS cache | 0–1 ms | — |
| 3 | Recursive resolver (cached) | 1–5 ms | — |
| 4–6 | Full DNS resolution (cold) | — | 20–120 ms |
| 7 | TCP handshake | — | 20–100 ms (1 RTT) |
| 8 | TLS 1.3 handshake | — | 50–150 ms (1 RTT) |
| 9 | CDN cache lookup | 1–5 ms (hit) | 5–20 ms (miss, forward) |
| 10 | Load balancer | 1–3 ms | 1–3 ms |
| 11 | Reverse proxy | 1–2 ms | 1–2 ms |
| 12 | Application server | 10–100 ms (simple) | 50–500 ms (complex) |
| 13 | Connection pool checkout | 0–1 ms | 0–5 ms (if waiting) |
| 14 | Database query | 1–10 ms (indexed) | 10–100 ms (complex) |

**Critical path**: For a cache miss to origin, DNS + TCP + TLS alone can be 100–200 ms before the first byte of HTTP. Application and database work add another 50–300 ms. Staff engineers use these numbers for SLA budgeting: "We have 200 ms for our service; DNS and networking eat 150 ms, so we have 50 ms for app + DB. We need to optimize."

**CDN as latency multiplier**: When the same resource is requested from many locations, a CDN can reduce latency dramatically. A user in Tokyo hitting an origin in Virginia might see 200 ms for a cache miss. A CDN edge in Tokyo serving the same content might see 20 ms. For static assets and cacheable API responses, the CDN effectively "moves" the server closer to the user. Staff engineers design cache keys and TTLs so that the maximum benefit is achieved—cache hits at the edge for the vast majority of requests.

### Why Staff Engineers Must Understand the Full Path

When users report "slow page loads," the cause could be:
- Slow DNS (wrong resolver, propagation)
- High RTT (users far from servers)
- Slow TLS (large cert, slow OCSP)
- Slow origin (DB, downstream services)
- Render-blocking resources, large JS

Staff engineers instrument each hop, measure p50/p95/p99, and optimize the slowest segments. They also design for failure at each hop: DNS failover, multiple CDN regions, health-based load balancing.

## ASCII Diagram: Request Lifecycle with Latency

```
    ┌────────────┐
    │   USER     │
    │ types URL  │
    └─────┬──────┘
          │
          │  DNS: 0-100ms (cached: 0ms)
          ▼
    ┌────────────┐
    │    DNS     │─────────────────────────────────────┐
    └─────┬──────┘                                     │
          │ Returns IP                                  │
          │                                             │
          │  TCP+TLS: 50-150ms (1-2 RTT)                │
          ▼                                             │
    ┌────────────┐     ┌────────────┐                   │
    │  TCP/TLS   │────►│   HTTP     │  Request sent     │
    │ Handshake  │     │  Request   │  ~few ms          │
    └────────────┘     └─────┬──────┘                   │
                            │                            │
                            │  Server processing:         │
                            │  10-500ms (or more)        │
                            ▼                            │
                     ┌────────────┐                      │
                     │  SERVER    │  DB, cache,          │
                     │ (LB→App)   │  external APIs       │
                     └─────┬──────┘                      │
                            │                             │
                            │  HTTP Response              │
                            │  ~few ms                    │
                            ▼                             │
                     ┌────────────┐                      │
                     │  BROWSER   │  Parse, render       │
                     │  Renders   │  ~50-200ms            │
                     └─────┬──────┘                      │
                            │                             │
                            ▼                             │
                     [User sees page]                     │
                     Total: ~100-1000ms typical           │
                                                         │
    CDN HIT: User ──► DNS ──► CDN Edge ──► Response      │
              (skips origin, 20-50ms total possible) ◄───┘
```

---

# Part 4: What is a Request and a Response?

## HTTP Request: Method, URL, Headers, Body

A typical HTTP request looks like:

```
POST /api/users HTTP/1.1
Host: api.example.com
Content-Type: application/json
Authorization: Bearer eyJ...
Content-Length: 52

{"name":"Alice","email":"alice@example.com"}
```

| Element | Purpose |
|---------|---------|
| **Method** | GET, POST, PUT, PATCH, DELETE, etc. — what action |
| **URL** | Path + query string — what resource |
| **Headers** | Auth, content type, caching hints, etc. |
| **Body** | Payload (for POST, PUT, PATCH) |

## HTTP Response: Status Code, Headers, Body

```
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/users/123

{"id":"123","name":"Alice","email":"alice@example.com"}
```

| Element | Purpose |
|---------|---------|
| **Status code** | 2xx success, 4xx client error, 5xx server error |
| **Headers** | Content type, cache control, etc. |
| **Body** | Payload (HTML, JSON, binary) |

## Request/Response is the Fundamental Pattern

The entire web—and most service-to-service communication—is built on this pattern: **client sends request, server sends response**. Synchronous by default. One request, one response (conceptually; HTTP/2 multiplexing changes this at the transport level).

## Synchronous vs. Asynchronous Request Patterns

| Pattern | Behavior | Example |
|---------|----------|---------|
| **Synchronous** | Client waits for response | REST API call, browser loading a page |
| **Asynchronous** | Client doesn't block; response via callback, poll, or event | Webhooks, message queues, Server-Sent Events |

Most user-facing APIs are synchronous: the user (or the frontend) waits for the result. Background jobs, notifications, and event-driven flows often use async patterns.

## Request Multiplexing (HTTP/2)

HTTP/1.1: one request per connection (unless pipelining, which had limited support). Many connections needed for parallel requests.

HTTP/2: **multiplexing**—multiple requests over a single connection, interleaved. Reduces connection overhead and head-of-line blocking at the HTTP layer. Critical for performance when a page needs many resources.

## Connection Keep-Alive and Its Importance at Scale

Without keep-alive, each HTTP request would require a new TCP (and TLS) connection. Connection setup adds latency and consumes server resources (file descriptors, memory).

With **keep-alive**, the TCP connection is reused for multiple requests. One TLS handshake serves many requests. At scale, this dramatically reduces:
- Latency (no repeated handshakes)
- Server load (fewer connections)
- Client load (fewer sockets)

**Staff-level implication**: Connection pooling (client-side) and appropriate keep-alive timeouts (server-side) are basic performance hygiene. Misconfiguration leads to connection exhaustion and 5xx errors under load.

**Connection exhaustion scenario**: An API server makes 1,000 concurrent requests to a downstream service. Without connection pooling, it opens 1,000 TCP connections. The downstream has a max of 500 connections. Result: half the requests fail or queue. With a connection pool of 50, the API reuses 50 connections—each handles requests in turn. The downstream stays within limits. The key is sizing: too small and you queue; too large and you overwhelm. Staff engineers tune pool size based on downstream capacity and observed latency.

## Request Lifecycle in a Microservice Architecture

One user action can trigger many internal calls:

```
    User clicks "Load Feed"
           │
           ▼
    ┌─────────────┐
    │   Client    │ 1. GET /feed
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ API Gateway │ 2. Authenticate
    └──────┬──────┘     → calls Auth Service
           │
           │ 3. Get feed
           ▼
    ┌─────────────┐
    │ Feed Service│ 4. Get user's follow list (User Graph Service)
    │             │ 5. Get posts (Post Service)
    │             │ 6. Get engagement (Engagement Service)
    │             │ 7. Rank (Ranking Service)
    └──────┬──────┘
           │
           │ 6. Response
           ▼
    [User sees feed]
```

**Fan-out**: One request triggers N downstream requests. If the feed service calls 5 other services for each request, and you have 10K QPS at the gateway, the feed service might emit 50K internal requests. Capacity planning must account for this **amplification**.

## Request Amplification and Fan-out

One of the most common mistakes in capacity estimation is assuming that "user QPS" equals "system QPS." In reality, a single user request often fans out to many internal requests. Staff engineers model this amplification explicitly—it drives provisioning, cost, and failure analysis.

### How 1 User Request Becomes 10–100 Internal Requests

A user action—clicking "Load Feed," opening a product page, placing an order—triggers a tree of internal calls. Each downstream service may call *its* dependencies. The **fan-out factor** is the average number of internal requests generated per user request. Typical numbers: 5–20 for a moderately complex API; 50–100+ for a rich feed or dashboard.

**Why it happens**:
- **Composition**: The API aggregates data from multiple domains (user, posts, media, engagement, recommendations).
- **Enrichment**: Each piece of data may require lookups (user profile, permissions, feature flags).
- **Validation**: Auth, rate limiting, audit logging—each adds a hop.
- **Redundancy**: Fallback calls when primary is slow or fails.

### Worked Example: User Opens Instagram Feed

A user opens the Instagram app and pulls to refresh the feed. One user action. What actually happens?

```
    User: "Pull to refresh"
         │
         │  1. Mobile app sends: GET /api/feed
         ▼
    ┌─────────────────┐
    │  API Gateway    │  →  Validates token, rate limit
    │                 │  →  Calls: Auth Service (validate JWT)
    └────────┬────────┘
             │  Internal: 1 call to Auth
             │
             │  2. Routes to Feed Service
             ▼
    ┌─────────────────┐
    │  Feed Service   │  →  Needs: current user, follow list, posts, media, engagement, ranking
    │                 │  →  Calls:
    │                 │      • User Service (get current user profile) — 1 call
    │                 │      • User Graph Service (get follow list, ~500 ids) — 1 call
    │                 │      • Post Service (get posts by ids, batched) — 1–3 calls (paginated)
    │                 │      • Media Service (get image URLs for each post) — 1–5 calls
    │                 │      • Engagement Service (likes, comments count per post) — 1–2 calls
    │                 │      • Ranking Service (score and order posts) — 1 call
    └────────┬────────┘
             │  Internal: 6–13 calls from Feed Service alone
             │
             │  Each downstream service may call *its* dependencies:
             ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  User Service   │  │  Post Service   │  │ Media Service   │
    │  → DB (user)    │  │  → DB (posts)   │  │ → CDN / Object  │
    │  → Cache        │  │  → Cache        │  │    Storage      │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Request tally for 1 user request**:

| Layer | Requests |
|-------|----------|
| API Gateway → Auth | 1 |
| API Gateway → Feed Service | 1 |
| Feed Service → User Service | 1 |
| Feed Service → User Graph Service | 1 |
| Feed Service → Post Service | 1–3 |
| Feed Service → Media Service | 1–5 |
| Feed Service → Engagement Service | 1–2 |
| Feed Service → Ranking Service | 1 |
| **Subtotal (Feed Service fan-out)** | **7–14** |
| Post Service → DB, cache | 2–6 |
| User Service → DB, cache | 1–2 |
| Media Service → Object Storage | 1–5 |
| **Total internal requests** | **~15–30** per user request |

In a rich implementation (A/B tests, analytics, ads, stories), the number can easily reach 50–100 internal requests per feed load.

### Total Internal QPS = User QPS × Fan-out Factor

| User QPS | Fan-out Factor | Internal QPS |
|----------|----------------|--------------|
| 100 | 10× | 1,000 |
| 1,000 | 15× | 15,000 |
| 10,000 | 20× | 200,000 |
| 100,000 | 25× | 2,500,000 |

**This is why capacity estimation matters.** If you provision for 10K "user requests" but each request triggers 20 internal calls, your backend must handle 200K QPS. Under-provisioning the feed service, post service, or database by 2× means cascading failures when traffic spikes.

### Why Staff Engineers Model Fan-out

1. **Provisioning**: Each service needs enough capacity for *its* share of the fan-out. The Feed Service sees 1× user QPS. The Post Service might see 3× (multiple calls per feed request). The database might see 10× (many services querying it).

2. **Latency**: End-to-end latency is bounded by the *critical path*—the longest chain of sequential calls. If the feed service calls 5 services in parallel, latency ≈ max(5). If it calls them sequentially, latency ≈ sum(5). Staff engineers parallelize where possible and optimize the slowest path.

3. **Failure**: If one of 10 downstream services is slow or down, what happens? Fail fast? Degrade gracefully? Timeout and partial response? The fan-out structure determines your failure handling strategy.

4. **Cost**: 1 user request = 20 internal requests = 20× the compute, database, and network cost. Unit economics depend on fan-out.

### Why This Matters: Request Amplification

| Scenario | User QPS | Internal QPS (if 5x fan-out) |
|----------|----------|------------------------------|
| 1K users, 1 req/s each | 1K | 5K |
| 100K users, 1 req/s each | 100K | 500K |
| 1M users, 1 req/s each | 1M | 5M |

If each downstream service has its own fan-out, the numbers grow further. Staff engineers model **request amplification** explicitly and ensure each layer can handle the load it will see, not just the user-facing QPS.

## ASCII Diagram: One User Request Fan-Out

```
    ┌──────────┐
    │  User    │  GET /feed
    │ Request  │
    └────┬─────┘
         │ 1
         ▼
    ┌─────────────┐
    │ API Gateway │
    └────┬────────┘
         │ 2
         ▼
    ┌─────────────┐
    │Feed Service │
    └────┬────────┘
         │
         │ 3a    3b    3c    3d    3e
         ▼      ▼     ▼     ▼     ▼
    ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
    │Auth │ │User │ │Post │ │Engage│ │Rank │
    │Svc  │ │Graph│ │Svc  │ │Svc   │ │Svc  │
    └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
       │       │       │       │       │
       │       │       │       │       │
       ▼       ▼       ▼       ▼       ▼
    ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
    │ DB  │ │ DB  │ │ DB  │ │ DB  │ │ ML   │
    └─────┘ └─────┘ └─────┘ └─────┘ └─────┘
    
    1 user request → 5+ service calls → potentially 5+ DB/ML calls
    Latency = critical path (often the slowest of 3a–3e)
    Capacity = must provision for fan-out at every layer
```

### L5 vs L6: Request/Response at Scale

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Latency** | "Our API responds in 50ms" | "Our API does 3 downstream calls; p99 is max(50, 80, 120) + overhead—we need to parallelize" |
| **Capacity** | "We need to handle 10K QPS" | "10K user QPS = 50K internal QPS; each downstream service needs capacity for its share" |
| **Failure** | "If a service is down, we return 500" | "If one of 5 dependencies is down, do we fail the whole request or degrade? What's the fallback?" |
| **Connection reuse** | "We use HTTP" | "We use connection pooling, keep-alive, and we've tuned pool size for our downstream QPS" |

---

# Part 5: L5 vs L6 Thinking About Systems

The difference between Senior (L5) and Staff (L6) engineers is rarely raw technical skill—it's scope, ownership, and system-level reasoning. The following comparison captures how each level approaches the same problems.

## Large Comparison Table: Senior vs Staff

| Dimension | L5 (Senior Engineer) | L6 (Staff Engineer) |
|-----------|----------------------|----------------------|
| **Scope** | "I'll build this service." | "What's the right system boundary? Who owns what? What are the failure modes across boundaries? How does this system evolve?" |
| **Ownership** | Owns implementation of a component. | Owns the system—boundaries, dependencies, evolution, cross-team alignment. |
| **Dependencies** | "We call the user service." | "The user service is in our critical path. We need circuit breakers, timeouts, fallbacks. We've documented our SLOs and their SLOs." |
| **Capacity** | "Our service handles 10K QPS." | "Our service handles 10K QPS, but each request fans out to 5 downstream services—we're responsible for 50K downstream QPS. We've modeled amplification." |
| **Failure** | "We have retries and timeouts." | "If the rate limiter fails, we fail open because availability trumps strict limiting. If the DB is slow, we shed non-critical reads. Here's our degradation matrix." |
| **Boundaries** | Works within given boundaries. | Defines boundaries. "Our system includes X; we treat Y as external. Here's how that affects SLAs." |
| **Scale** | "We'll add more replicas." | "We'll add replicas until we hit DB limits. Then we need read replicas, caching, or sharding. Here's the migration path." |
| **Evolution** | "We'll refactor when needed." | "This design allows us to split the service in 18 months without breaking consumers. We've versioned the API." |
| **Debugging** | "The logs show an error in our service." | "The trace shows 200ms in our service, 800ms in the payment provider. Our timeout is 2s—we're not the bottleneck. The payment team needs to investigate." |
| **Interview** | Describes components and implementation. | Starts with boundaries, request path, failure modes, trade-offs. Connects design to business impact. |

## Detailed Examples: L5 vs L6 in Practice

### Example 1: Building a Rate Limiter

**L5**: "I'll build a rate limiter. It will use a sliding window algorithm and Redis for state. It'll support 10K requests per minute per user."

**L6**: "We need a rate limiter at the API gateway. Before building, I'm defining the boundary: the limiter is *our* system; Redis is a dependency. If Redis is down, we fail open—we'd rather allow excess traffic than block everything. We'll expose metrics for both allowed and rejected requests. The blast radius of a bug is all API traffic, so we'll canary carefully. We're not building a global rate limiter—that's a different system with different consistency needs."

### Example 2: Database as Bottleneck

**L5**: "The database is slow. We'll add an index and optimize the query."

**L6**: "The database is the bottleneck. Here's the read/write ratio: 95% reads. We'll add read replicas and route reads there. We need to handle replication lag—for strict consistency we'll keep those reads on the primary. We've profiled: the top 3 queries account for 80% of load. We'll add a cache for the hottest one. When we hit write limits, we'll shard by user_id. I've documented the migration path so we're not scrambling when the time comes."

### Example 3: New Feature Request

**L5**: "We need to add a 'recommended for you' section. I'll add an endpoint that calls the recommendation service and returns the results."

**L6**: "Before adding the endpoint: What's the system boundary? Is the recommendation service ours or another team's? If it's theirs, we need an SLA and fallback—maybe show trending instead of personalized when they're down. What's the fan-out? One recommendation call per request, or does it call 5 sub-services? We need to know for capacity. And latency—recommendations can be slow. Do we block the whole page or load them async? I'll propose a design that considers all of this."

### Example 4: Incident Response

**L5**: "The API is returning 500s. Our service looks fine—maybe it's the database?"

**L6**: "We're seeing 500s. From the trace: requests are timing out at the payment service. Our timeout is 5s; the payment service is taking 8s. We're not the root cause—we're the victim. But we're not innocent: we should have a circuit breaker. After 50% failure rate, we'll stop calling payment and return a degraded response ('payment temporarily unavailable'). I'll draft a post-incident that covers: why payment was slow (their problem), why we cascaded (our lack of circuit breaker), and the remediation."

## The Core Shift: Component → System

- **L5** thinks in components: "I own this piece. I'll make it good."
- **L6** thinks in systems: "I own how this piece fits in the whole. I'll make the system work, including when components fail."

In interviews, demonstrating L6 thinking means: Start with boundaries. Trace the request path. Identify failure modes. Discuss trade-offs. Connect technical choices to business and operational outcomes. Don't jump to "I'll build a Redis cache" before establishing *what* you're building, *for whom*, and *what happens when it breaks*.

### The Feedback Loop: Systems Evolve

Staff engineers don't just design for today—they design for evolution. A system that works at 1K QPS may need different boundaries at 100K QPS. A service that was "inside" might be split out when a new team forms. The API contract you define today constrains—or enables—future changes. Document not only what the system is, but what assumptions would trigger a redesign. "If our fan-out grows beyond 20×, we'll need to introduce aggregator services." "If we add a new client type with different latency requirements, we may need a dedicated BFF." This forward-looking awareness distinguishes Staff thinking from Senior.

---

# Example in Depth: One Request Through a Real System

To make the abstract concrete, here is a **single user action** traced through a real-world-style system: **viewing a product page on an e-commerce site** (think Amazon, Flipkart, or a similar marketplace). Every number and hop is illustrative but realistic.

## The User Action

User clicks **"View product"** for one item. One click. One URL.

## What Actually Happens (Step by Step)

| Step | Component | What happens | Typical latency | Notes |
|------|-----------|--------------|-----------------|--------|
| 1 | Browser | Parse URL, check cache (service worker, HTTP cache) | 0–5 ms | Cache hit: return cached page; miss: continue |
| 2 | DNS | Resolve product-site.com (often cached at OS or resolver) | 0–50 ms | GeoDNS may return nearest CDN IP |
| 3 | CDN (e.g. CloudFront) | Request for `/product/123`. Edge checks cache. | 1–5 ms | **Cache HIT**: HTML/static from edge → skip origin. **MISS**: forward to origin |
| 4 | Load balancer | Receives request from CDN (origin request) | 1–2 ms | Picks one of N frontend or API servers |
| 5 | API Gateway / BFF | Validates session, resolves product ID, may call multiple backends | 5–20 ms | Often the orchestrator: auth, then fan-out |
| 6 | Product service | Get product details (name, price, images) | 10–30 ms | Reads from DB or cache; cache hit ~1 ms |
| 7 | Inventory service | Get stock level ("In stock", "Only 3 left") | 10–50 ms | May be separate DB or cache |
| 8 | Review service | Get rating and recent reviews (or summary) | 20–80 ms | Often one of the slowest (aggregation, many rows) |
| 9 | Recommendation service | "Customers also bought" | 20–100 ms | May use ML or rules; can be async or deferred |
| 10 | Image/Media service | Resolve image URLs (already in product payload or separate) | 5–20 ms | URLs often point back to CDN for actual bytes |
| 11 | Database(s) | Product DB, inventory DB, review DB (each may have replicas/cache) | 1–50 ms per query | p99 can be 100+ ms if cold or under load |
| 12 | Response assembly | BFF/API aggregates responses, builds JSON or HTML | 2–10 ms | |
| 13 | Back to user | Response travels: origin → CDN → user | 20–150 ms | Depends on user ↔ CDN RTT |

**Total (typical)**: 100–400 ms for a product page. **p99** can be 1–2 seconds if any dependency is slow or cache misses spike.

## The Numbers That Matter for Design

- **One user request** → **5–10+ internal service calls** (product, inventory, reviews, recommendations, auth). So 1,000 product-page views per second can mean **5,000–10,000+** internal RPS. Staff engineers use this to size backends and databases.
- **Cache hit rate**: If product and inventory are cached at 90%, the database sees 10% of the traffic. That 10% still must be within DB capacity; if cache fails or is cold, traffic hits DB fully—**thundering herd**.
- **Slowest dependency**: Often reviews or recommendations. If review service p99 is 500 ms, the whole page waits. So: **timeouts**, **parallel calls**, and **degradation** (e.g. show "Reviews loading..." or skip recommendations if timeout).

## Breadth: Failure at Every Hop, Edge Cases, and Anti-Patterns

Systems fail at every layer. Staff-level thinking means knowing **what can go wrong** and **what to do**.

| Hop | What can go wrong | Consequence | Mitigation / design |
|-----|-------------------|-------------|----------------------|
| DNS | Hijack, misconfiguration, DDoS on nameservers | Users can't reach you or get wrong IP | Multiple DNS providers, low TTL in crisis, GeoDNS/Anycast |
| CDN | Edge outage, cache poisoning, origin unreachable | Slower or failed page loads | Multi-CDN or failover, validate before cache, origin health |
| Load balancer | Overload, misconfiguration, no healthy backends | 5xx, timeouts | Redundant LBs, health checks, circuit breakers |
| API Gateway / BFF | Timeout to one backend, auth service down | Partial or failed response | Timeouts per backend, fallbacks, degrade (e.g. skip reviews) |
| Product / Inventory / Review services | DB slow, cache miss storm, bug | High latency or errors | Read replicas, cache, backpressure, kill switches |
| Database | Full, replica lag, deadlock, OOM | Writes fail, stale reads, timeouts | Connection pooling, monitoring, failover, capacity headroom |

**Edge cases worth naming:**

- **Thundering herd**: Cache expires for a hot key; 10,000 requests hit DB at once. Use **probabilistic early expiry**, **single-flighter** (one request refreshes, others wait), or **stale-while-revalidate**.
- **Cascading failure**: One backend is slow; callers wait; their threads/connections fill; callers start failing. Use **timeouts**, **circuit breakers**, and **per-dependency limits** (bulkheads).
- **Wrong boundary**: Treating a third-party (e.g. payment provider) as "in our system" for SLA. Define **external** vs **owned**; document dependency SLAs and user impact.
- **No timeouts**: A call to a slow service blocks forever. **Always set timeouts** on every outbound call and define fallback (error, default, or degraded response).

**Anti-patterns:**

- **"Our system is the monolith"**: Ignoring that one user request triggers many internal and external calls. Capacity and failure mode analysis must include **full request path** and **fan-out**.
- **"We'll add caching later"**: Hot path without caching often becomes the first production fire. Design cache strategy (what to cache, where, TTL, invalidation) with the initial design.
- **"If the DB is slow we'll scale it"**: Single DB has a ceiling. Staff engineers plan **read replicas**, **sharding**, or **different stores** before hitting the ceiling.

---

# Summary: From Basics to Staff-Level Thinking

The concepts in this chapter—systems, servers, clients, the URL journey, request/response—are simple. What separates Staff-level thinking is the ability to:

1. **Define system boundaries** explicitly and reason about dependencies and ownership
2. **Trace the full request path** and attribute latency and failure to specific hops
3. **Account for request amplification** when doing capacity planning
4. **Understand that servers and clients are roles**, not fixed—and design for the full call chain
5. **Connect simple mechanics** (DNS, TCP, TLS, HTTP) to real-world trade-offs (CDN, keep-alive, multiplexing)

Use this foundation to build. When you design a system, start with: What are the components? What are the boundaries? What is the request path? What amplifies? What fails? The answers will shape everything that follows.

---

# Interview Application: How These Basics Appear in Staff Interviews

System design interviews at Staff level often begin with broad prompts: "Design a URL shortener," "Design a rate limiter," "Design a feed system." The difference between a strong and weak answer is often in the *opening*—whether the candidate jumps to components or establishes foundations first.

## When Asked to Design a System: Start Here

**Step 1: Define the system boundary.**  
Before drawing a single box, say: "I'm defining our system to include X, Y, Z. We'll treat A and B as external dependencies." Example: "For a notification system, our boundary includes the routing logic, queue, and retry mechanism. We'll treat FCM, SendGrid, and APNs as external—we integrate with them but don't operate them."

**Step 2: Identify clients.**  
"Who are the clients? Browsers, mobile apps, other services, cron jobs?" This drives API design, auth, and rate limiting. "For a rate limiter, clients are our own API gateways—internal. For a public API, clients are third-party developers—we need different limits and documentation."

**Step 3: Understand the full request path.**  
"Let me trace a typical request." Walk through: client → DNS → CDN? → load balancer → API gateway → service(s) → database. Name each hop. "For a feed request, the path is: mobile app → our API → auth check → feed service → user service, post service, ranking service → response. Latency is dominated by the slowest of those parallel calls."

**Step 4: Then design components.**  
Only after boundaries, clients, and request path are clear should you dive into "we'll use Redis for the rate limit counters" or "we'll use a B-tree index on user_id."

## How Interviewers Probe for These Basics

| Interview Question | What They're Testing | Strong Answer |
|--------------------|---------------------|---------------|
| "What happens when a user hits your API?" | Can you trace the full path? | "User request hits our CDN—cache miss—goes to load balancer, API gateway. Gateway validates auth, routes to the feed service. Feed service calls user, post, and ranking services in parallel. Latency is max of those three plus overhead." |
| "How do you handle 10x traffic?" | Do you understand capacity and amplification? | "10x user traffic could mean 50x internal traffic due to fan-out. We'd need to scale the API gateway, each backend service, and the database. The DB is likely the bottleneck—we'd add read replicas and possibly sharding." |
| "What if the database goes down?" | Do you think in failure modes? | "If the primary goes down, we fail over to a replica. During failover, we'll have a few seconds of errors. We've documented this in our SLA. For read-heavy workloads, we could serve from cache with stale data, but writes would fail." |
| "Where do you draw the line for your system?" | Do you define boundaries? | "Our system includes our API, services, and database. We treat payment (Stripe) and email (SendGrid) as external. If Stripe is down, payments fail—we're transparent about that. We have a status page that reflects both our status and key dependencies." |

## Common Mistakes to Avoid

- **Jumping to technology**: "We'll use Kafka" before establishing what problem you're solving. Start with requirements and boundaries.

- **Ignoring the request path**: Designing components in isolation without tracing how a request flows through them. The path reveals bottlenecks and failure points.

- **Underestimating fan-out**: "We need to handle 1K QPS" when each request triggers 20 internal calls. Capacity planning must account for amplification.

- **Vague boundaries**: "Our system has a database and some services." Be explicit: "Our system includes the order service, inventory service, and order DB. Payment is external."

- **No failure discussion**: Only describing the happy path. Staff interviews expect: "If X fails, we do Y. Here's our degradation strategy."

## Opening Phrases That Signal Staff-Level Thinking

- "Before I design, let me clarify the boundaries..."
- "Let me trace the request path first..."
- "The key trade-off here is..."
- "If this component fails, the blast radius is..."
- "We'd need to account for fan-out—each user request triggers N internal calls..."
- "Our SLA would be the product of component SLAs—99.9% × 99.9% = 99.8%..."

Use these deliberately. They signal that you think in systems, not just components.

### How to Practice for the Basics

1. **Trace a real request**: Pick a product you use (e.g., loading a feed, placing an order). Draw the request path from browser to database. Name every hop. Estimate latency at each. Identify where it could fail.

2. **Define boundaries for a hypothetical system**: "Design a notification system." Before drawing boxes, write down: What's in our boundary? What's external? Who are the clients? What's the SLA we're accountable for?

3. **Model fan-out**: For a feed or dashboard, estimate: 1 user request → how many internal calls? Multiply by expected QPS. That's your internal load. Does your design handle it?

4. **Review past incidents**: When something broke, could you trace it to a specific hop? Could you articulate the blast radius? Practice explaining incidents in system terms.

---

# Interview Takeaways: What to Demonstrate

When discussing these basics in an interview, Staff-level candidates:

- **Draw the system boundary** before drawing components: "I'm defining our system to include the API, the core services, and our database—but not the payment provider or CDN, which we'll treat as external dependencies."
- **Trace a request end-to-end** and name each hop: "User request hits our CDN, then load balancer, then API gateway, which fans out to auth, user service, and feed service. The feed service calls the post service and the engagement service. Latency is dominated by the slowest of those."
- **Give numbers** when possible: "A typical request does 2–3 DB queries and 1–2 external API calls. At 10K QPS, that's 20–30K DB queries per second—our primary can handle that with read replicas for the heavy reads."
- **Discuss failure modes** at each layer: "If DNS fails, we're down. If the CDN fails, we fall back to origin but latency increases. If one backend service is slow, we need timeouts and fallbacks so we don't block the whole request."
- **Connect basics to design decisions**: "We chose connection keep-alive and HTTP/2 so that the mobile app can multiplex many API calls over one connection, reducing latency for feed loading."

The interviewer is listening for: Can you move from concept to implication? From "what" to "why it matters"?

**Final thought**: The basics—systems, servers, clients, the URL path, request amplification—are not interview trivia. They are the foundation upon which every distributed system is built. A candidate who can articulate boundaries, trace requests, model fan-out, and reason about failure modes demonstrates the kind of system thinking that defines Staff level. Master these, and the more advanced topics—consistency, scaling, observability—will rest on solid ground. When in doubt, start with the basics: define the system boundary, identify the clients, trace the request path, and account for amplification. Everything else follows from there.
