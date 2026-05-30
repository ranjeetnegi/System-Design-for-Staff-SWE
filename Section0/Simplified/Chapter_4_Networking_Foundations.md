# Chapter 4: Networking Foundations — HTTP, TCP, Sockets, and the OSI Model

---

## 1. Learning Goal

After reading this chapter, you will be able to:

- Explain the OSI model and identify which layers matter most in practice
- Describe the difference between TCP and UDP, and when to use each
- Explain what a socket is and why connections are expensive
- Describe why connection pooling and keep-alive are essential at scale
- Explain the difference between bandwidth and latency, and why they solve different problems
- Debug network failures by identifying which layer the problem is in

---

## 2. Why This Matters

Every request in a distributed system travels over a network. When a request fails, times out, or is slow, the cause could be at any layer of the network stack. Staff engineers must be able to:

- Say "this is a Layer 4 problem" (TCP connection refused) vs "this is a Layer 7 problem" (wrong HTTP status code)
- Estimate whether a design will work given the expected network latency between services
- Design systems that reuse connections efficiently to avoid paying handshake costs on every request
- Understand why some users in Asia see 200 ms latency when users in the US see 20 ms

Without networking fundamentals, you cannot debug production issues, estimate system latency, or make informed architectural decisions about where to place services.

---

## 3. Core Concepts

### The OSI Model: 7 Layers of Networking

Networks are complex. To manage this complexity, engineers use a model that divides networking into layers. Each layer has one responsibility.

The **OSI model** has 7 layers:

| Layer | Name | Job | Real examples |
|-------|------|-----|---------------|
| 7 | Application | What the user wants | HTTP, DNS, SMTP |
| 6 | Presentation | Format and encrypt | TLS/SSL, JSON encoding |
| 5 | Session | Manage conversations | Sessions, authentication |
| 4 | Transport | Reliable delivery | TCP, UDP |
| 3 | Network | Routing between machines | IP addresses, routers |
| 2 | Data Link | Local network connections | Ethernet, WiFi, MAC addresses |
| 1 | Physical | Actual signals | Cables, fiber, radio waves |

**In practice, you care most about two layers:**
- **Layer 4 (Transport): TCP and UDP** — how connections work
- **Layer 7 (Application): HTTP** — how your API communicates

**Memory trick** (bottom to top): "**P**lease **D**o **N**ot **T**hrow **S**ausage **P**izza **A**way" = Physical, Data Link, Network, Transport, Session, Presentation, Application.

---

### Why Layers Help You Debug

When something breaks, the layer tells you where to look:

| Error message | Layer | Where to look |
|---------------|-------|---------------|
| "Connection refused" | L4 | Server is not listening on that port. Check if service is running. Check firewall. |
| "Connection timeout" | L4/L3 | TCP handshake never completed. Check network path, firewall, server load. |
| "502 Bad Gateway" | L7 | Server received a request but upstream returned garbage. Check the upstream service. |
| "503 Service Unavailable" | L7 | Application is overloaded or down. Check application health. |
| Cannot reach server at all | L3 or below | Wrong IP, broken route, cable unplugged. Use ping and traceroute. |

**Staff-level debugging practice:** Start at Layer 7 (application) and work down. "We get 502" → look at the application. "Connection timeout" → check the network. "No connectivity at all" → check physical and routing.

---

### TCP: Reliable, Ordered Delivery

**TCP** (Transmission Control Protocol) guarantees that:
- Every byte of data arrives (lost packets are retransmitted)
- Data arrives in the correct order
- Neither side is overwhelmed (flow control)

**The cost:** Before sending any data, TCP requires a **three-way handshake**:

```
Client ──── SYN ────────────────► Server
Client ◄─── SYN-ACK ─────────── Server
Client ──── ACK ────────────────► Server

[Now data can flow]
```

This handshake takes one **RTT (round-trip time)**. If the server is 50 ms away, the handshake alone costs 50 ms before your first byte of application data.

**TCP overhead:**
- Handshake: 1 RTT (50–200 ms depending on distance)
- TLS handshake on top: 1–2 more RTT (another 50–400 ms)
- Total before first byte: 2–3 RTT on a cold connection

**Head-of-line blocking:** If one TCP packet is lost, all subsequent packets wait until the lost one is retransmitted. This is why HTTP/2, which sends multiple requests over one TCP connection, can still have latency spikes when a packet is lost.

---

### UDP: Fast, No Guarantees

**UDP** (User Datagram Protocol) is the opposite of TCP:
- No handshake — just send data
- No guarantee packets arrive
- No guarantee of ordering
- No retransmission of lost packets

**8-byte header** vs TCP's 20+ byte header. Much lower overhead.

**When to use UDP:**
- **Video streaming**: A lost video frame is acceptable. A 100 ms delay to retransmit is not. Better to show a glitch for a frame than to pause for a second.
- **Online games**: Player position updates happen many times per second. An old position is useless — just send the new one. If a packet is lost, the next one will arrive in milliseconds.
- **Voice calls (VoIP)**: A tiny glitch is better than lag. Real-time.
- **DNS queries**: Small request, small response. One packet each way. UDP is simpler.

**Summary:**
- TCP = registered mail (guaranteed delivery, signed receipt, but slower)
- UDP = postcard (fast, no tracking, might get lost)

---

### QUIC and HTTP/3

**HTTP/2** uses TCP. When one packet is lost in a TCP connection, all streams in that connection stall.

**HTTP/3** is HTTP over **QUIC** — a protocol built on top of UDP. QUIC implements its own reliability and ordering **per stream**. So:
- Stream A loses a packet → only Stream A waits
- Streams B, C, D continue without interruption

HTTP/3 eliminates TCP's head-of-line blocking while keeping reliability where needed. It also combines the TCP handshake and TLS handshake into one step, reducing connection setup time.

**Use case for HTTP/3:** Mobile networks and international connections where packet loss is common. Users on poor networks see much better performance.

---

### What Is a Socket?

A **socket** is an endpoint for communication. It is identified by an IP address plus a port number.

Example: `93.184.216.34:443`
- `93.184.216.34` → the machine (IP address)
- `443` → the service on that machine (port)

Common port numbers:
- 80 → HTTP
- 443 → HTTPS
- 22 → SSH
- 3306 → MySQL
- 5432 → PostgreSQL
- 6379 → Redis

A TCP **connection** links two sockets:
- Client socket: `192.168.1.10:54321` (client IP + randomly assigned port)
- Server socket: `93.184.216.34:443` (server IP + service port)

The server runs `listen()` on port 443 and waits. When a client calls `connect()`, the server accepts and a connection is established. Each side can now send and receive data.

---

### Why Connections Are Expensive

Opening a new TCP connection has a significant cost:

1. **DNS lookup**: 0–100 ms (often cached)
2. **TCP handshake**: 1 RTT (50–200 ms depending on distance)
3. **TLS handshake**: 1–2 RTT (another 50–400 ms)
4. **Database authentication** (if connecting to a DB): 1 more round-trip

**Total for a new HTTPS connection: 100–600 ms** before any data is exchanged.

For a request that takes 5 ms to process, you could be paying 100x the processing time just in connection setup.

**Connection pooling** solves this by keeping connections open and reusing them. Instead of creating a new connection for every request, you take an idle connection from a pool, use it, and return it. HikariCP (a Java connection pool) can hand out a connection in 250 **nanoseconds** — 40,000x faster than creating a new one.

---

### HTTP Keep-Alive and Multiplexing

**HTTP/1.1 keep-alive:** By default, HTTP/1.1 keeps the TCP connection open after a request completes. The next request reuses the same connection — no TCP or TLS handshake needed.

**HTTP/2 multiplexing:** HTTP/2 sends multiple requests over a single TCP connection simultaneously. Instead of opening 6 connections to load 6 resources (HTTP/1.1 behavior), you open 1 connection and send 6 streams in parallel.

```
HTTP/1.1: 6 resources = 6 TCP connections (or 6 sequential requests on one connection)
HTTP/2:   6 resources = 1 TCP connection, 6 parallel streams
```

**Why this matters:** Connection establishment is expensive. Reusing connections reduces latency dramatically. At scale, reducing connection overhead also reduces load on both client and server.

---

### HTTP Methods and Status Codes

(These were covered in Chapter 2. Key reminders for networking context:)

**GET** is cacheable by CDNs and browsers. CDNs can serve GET responses from edge locations near users without hitting your origin servers.

**POST, PUT, DELETE** are not cached. They always reach your origin server.

**Status codes for networking/retry logic:**
- **5xx** → server error → safe to retry (the problem is on the server side)
- **429** → rate limited → retry after waiting (with exponential backoff)
- **4xx** → client error → do NOT retry (fixing the request is your job)

---

### Bandwidth vs Latency

These are the two fundamental measures of network performance. They are different and solve different problems.

**Bandwidth** = how much data can flow per second. Think of a pipe's width.
- Units: Mbps (megabits per second), Gbps (gigabits per second)
- Example: Home internet 100 Mbps, datacenter link 10 Gbps

**Latency** = how long it takes for one packet to travel from A to B. Think of a pipe's length.
- Units: milliseconds (ms)
- Determined by physics: the speed of light in a fiber cable
- New York to Tokyo: light travels ~140 ms round-trip. No engineering can change this.

**Which one matters for your use case?**

| Request type | Typical size | Dominant factor |
|-------------|-------------|----------------|
| API call (JSON) | 1–10 KB | Latency (time to first byte) |
| Web page | 2–3 MB | Both (latency for first byte, bandwidth for body) |
| Video stream | GB/hour | Bandwidth (continuous data) |
| Database query result | 10 KB | Latency |
| File download | 100 MB | Bandwidth |

**Key insight:** For small requests (under 100 KB), bandwidth is almost never the bottleneck. Even a 1 Mbps connection can transfer 10 KB in 80 milliseconds. But a 100 ms RTT (round-trip time) costs 100 ms regardless of bandwidth.

**For interactive systems (search, feed, payments):** Optimize for latency.
**For bulk data (backups, video, large file downloads):** Optimize for bandwidth.

---

### Cross-Region Latency

Network latency is dominated by physical distance. Light travels at about 300,000 km/second in a vacuum — slower in fiber cables.

| Route | Approximate RTT |
|-------|----------------|
| Same datacenter | 0.1–0.5 ms |
| Same city | 1–5 ms |
| New York ↔ Los Angeles | ~70 ms |
| New York ↔ London | ~80 ms |
| New York ↔ Tokyo | ~140 ms |
| Europe ↔ Asia | ~130 ms |

**Why this matters for design:** If your API server is in Virginia (US East) and a user is in Tokyo, every request takes 140 ms round-trip just for the network. Add TCP handshake (140 ms), TLS handshake (140 ms), and you have 420 ms before the first byte of your response.

**Solution: Put servers closer to users.** This is done with:
- **CDNs** (Content Delivery Networks): Cache static content at edge locations near users
- **Regional deployments**: Deploy your API servers in multiple regions (US, Europe, Asia)
- **Geo-DNS**: Route users to the nearest region automatically
- **Anycast**: The same IP address is served from multiple physical locations; BGP routing sends each user to the nearest one

---

## 4. Mental Models

### The Postal Mail Analogy

| Networking | Postal service |
|-----------|---------------|
| TCP | Registered mail — guaranteed delivery, signed receipt, but slower |
| UDP | Postcard — fast, no tracking, might get lost |
| HTTP request | The letter inside the envelope |
| IP address | Street address on the envelope |
| Port number | Apartment number in the building |
| DNS | Phone book (name → address) |

### The Pipe Analogy for Bandwidth vs Latency

```
BANDWIDTH = Width of the pipe
LATENCY   = Length of the pipe

Bandwidth:   [======pipe width======]
Latency:     [.....pipe length.....]

You can make a wide pipe (more bandwidth)
but you cannot make a shorter pipe (physics limits distance)

For small requests: latency dominates (pipe length matters)
For large transfers: bandwidth dominates (pipe width matters)
```

---

## 5. Real-World Example: The Complete Request from Tokyo to Virginia

A user in Tokyo loads a page from an API server in Virginia. Here is where every millisecond goes:

| Step | Time | Notes |
|------|------|-------|
| DNS lookup (cached) | 0–5 ms | Usually cached after first visit |
| TCP handshake | ~140 ms | One RTT, Tokyo–Virginia |
| TLS handshake (TLS 1.3) | ~140 ms | One RTT |
| HTTP request sent | ~1 ms | Small payload, quick |
| Server processing | ~50 ms | Query database, compute response |
| Response travels back | ~140 ms | One RTT |
| **Total (cold connection)** | **~476 ms** | |
| **Total (warm connection, reused)** | **~191 ms** | Save 140+140 ms = 280 ms |

**Key learning:** Reusing connections saves 280 ms on every request for this user. This is why connection keep-alive and connection pooling are critical, especially for users far from your servers.

**What you can do:**
- Deploy a CDN edge node in Tokyo (now users hit a server 5 ms away instead of 140 ms)
- Use HTTP/2 to send multiple requests over one connection (saves handshake for subsequent requests)
- Enable TLS 1.3 (saves one RTT vs TLS 1.2)
- Pre-warm connections with a connection pool

---

## 6. Design Trade-offs

### TCP vs UDP: The Decision

| Question | Answer | Protocol |
|----------|--------|----------|
| Must every byte arrive? | Yes | TCP |
| Is a missed packet unrecoverable? | Yes | TCP |
| Is low latency more important than completeness? | Yes | UDP |
| Is an old packet less useful than no packet? | Yes | UDP |

**Examples:**
- Payment API → TCP (every byte must arrive)
- Database connection → TCP (data integrity critical)
- Live video stream → UDP (better to show glitch than to pause)
- Online game position updates → UDP (old data is worthless)

### Connection Pool Sizing

Too small: Requests queue waiting for a connection → latency spikes.
Too large: Database is overwhelmed by too many connections → slow for everyone.

**Rule of thumb for databases:**
- Pool size per app instance: 10–30 connections
- Total connections = pool size × number of instances
- Must be less than database `max_connections`

If you have 50 app instances with a pool of 20 each = 1,000 total connections. If your database `max_connections` is 100, you will get "too many connections" errors. Use PgBouncer to proxy hundreds of app connections into a small number of actual database connections.

---

## 7. Common Interview Questions

1. **"You see 'connection refused' errors from service A to service B. How do you debug?"**
   Expected: Layer 4 problem. Check if service B is running and listening on the expected port. Check firewall rules. Check if the correct host and port are configured. Use `telnet host port` or `nc` to test.

2. **"Your p99 latency spikes exactly every 30 seconds by 500 ms. What is the cause?"**
   Expected: TCP keepalive timeout. Load balancer might be silently closing idle connections after 30 seconds. When the next request tries to use the dead connection, it gets a reset and must retry. Fix: set application keepalive shorter than the load balancer timeout.

3. **"Users in Asia have 200 ms higher latency than users in the US. How do you fix this?"**
   Expected: Physics — 140 ms RTT New York to Tokyo. Add an Asia deployment region or CDN edge. Route Asian users to closer servers. Cannot be fixed with faster code.

4. **"Why is HTTP/3 better than HTTP/2 for mobile users?"**
   Expected: Mobile networks have higher packet loss. HTTP/2 over TCP: one lost packet blocks all streams in the connection. HTTP/3 over QUIC (UDP): only the affected stream pauses; other streams continue.

5. **"A client retries a POST request after a timeout. What could go wrong?"**
   Expected: The first request may have already been processed (the server processed it but the response was lost). The retry creates a duplicate (double order, double charge). Solution: idempotency keys.

---

## 8. Key Takeaways

**Layer 4 (TCP) vs Layer 7 (HTTP) is your first debugging question.** "Connection refused" → TCP problem. "502 Bad Gateway" → HTTP/application problem. Know the layer and you know where to look.

**TCP is reliable but costs 1–3 RTT to start.** On a cold connection, handshakes alone take 100–400 ms. Always reuse connections with keep-alive and connection pools.

**UDP is fast but unreliable.** Use it when low latency matters more than completeness (video, gaming, voice). HTTP/3 builds reliability on top of UDP to get the best of both.

**Bandwidth vs latency:** For API calls (small payloads), latency dominates. More bandwidth does not help if the round-trip time is 140 ms. For large file transfers, bandwidth dominates. Optimize the right one.

**Physics limits latency.** New York to Tokyo is 140 ms by light. No code change fixes this. Move servers closer to users with regional deployment, CDN, or Anycast.

**Connection reuse is critical.** A new HTTPS connection costs 100–600 ms. A reused connection adds near-zero overhead. At scale, connection efficiency makes the difference between fast and slow.

**L5 vs L6 thinking:**
- L5: "Our API is slow for users in Asia."
- L6: "Tokyo–Virginia RTT is 140 ms. With TCP + TLS handshake, each cold connection costs ~420 ms before first byte. We need either a CDN edge node in Tokyo (cuts to ~10 ms RTT) or an Asia deployment. Our current p99 from Asia is 600 ms; deploying to ap-southeast-1 would cut it to under 150 ms. Here is the migration plan."
