# Basics Chapter 4: Networking Foundations — HTTP, TCP, Sockets, and the OSI Model

---

# Introduction

Every system you design—every API, every microservice, every distributed architecture—rests on networking fundamentals. When a request times out, is it a DNS issue, a TCP handshake problem, or an application-layer failure? When users in Asia experience high latency, is it bandwidth or round-trip time? Staff engineers can answer these questions because they understand the **layers** of networking and where each problem lives.

This chapter builds that foundation. We'll cover the OSI model (and which layers actually matter), TCP vs UDP (and when each wins), sockets and connections (and why connection pooling is non-negotiable), HTTP methods and status codes (and why idempotency matters for retries), and bandwidth vs latency (and why you can't fix one with the other). By the end, you'll have the vocabulary and mental models to debug production issues and design systems that respect the realities of the network.

---

# Quick Visual: The Layers That Matter

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NETWORKING: WHERE PROBLEMS LIVE                            │
│                                                                             │
│   L7 Application   HTTP, REST, gRPC   ← Your API logic, status codes        │
│   L4 Transport     TCP, UDP          ← Connections, retransmission, flow   │
│   L3 Network       IP, routing       ← Where packets go, routing loops       │
│   L2 Data Link     MAC, switches     ← Local network, NIC                   │
│   L1 Physical      Cables, radio     ← Signal, link down                   │
│                                                                             │
│   When debugging: "Is it L7 (bad status)? L4 (connection refused)?         │
│   L3 (routing)? L1 (cable unplugged)?" — Each layer, different fix.         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 1: The OSI Model — 7 Layers Simplified

## From Physical Wires to Your Application

The **OSI (Open Systems Interconnection) model** divides networking into seven layers. Each layer has a job. Data flows down (from application to physical) when sending, and up (from physical to application) when receiving. Understanding which layer a problem exists at helps you know where to look—and what to fix.

| Layer | Name | Purpose | Examples |
|-------|------|---------|----------|
| **7** | Application | User-facing data, application logic | HTTP, HTTPS, gRPC, WebSocket, DNS |
| **6** | Presentation | Format, encryption, compression | TLS/SSL, JSON/XML encoding |
| **5** | Session | Connection lifecycle, session management | APIs that manage sessions |
| **4** | Transport | End-to-end delivery, reliability | TCP, UDP |
| **3** | Network | Routing, logical addressing | IP, routers |
| **2** | Data Link | Local network, physical addressing | Ethernet, MAC, switches |
| **1** | Physical | Actual signal on wire or radio | Cables, fiber, WiFi radio |

**Mnemonic** (bottom to top): **P**lease **D**o **N**ot **T**hrow **S**ausage **P**izza **A**way — Physical, Data Link, Network, Transport, Session, Presentation, Application.

## The Practical Layers for System Design

In practice, system designers care most about:

- **Layer 4 (Transport)**: TCP vs UDP. Connection setup. Retransmission. Flow control. Head-of-line blocking.
- **Layer 7 (Application)**: HTTP methods, status codes, headers, REST, API design.

Layers 5 and 6 are often folded into L7 (e.g., TLS happens "at" the application layer in the TCP/IP model). Layers 1–3 are typically handled by infrastructure—you configure routing and switches, but most application debugging focuses on L4 and L7.

## Why Staff Engineers Care

When a request fails, the first question is: **which layer?**

- **Connection refused** → L4. The server isn't listening, or a firewall is blocking.
- **Connection timeout** → L4 or L3. TCP handshake never completes; could be network path, firewall, or server overload.
- **502 Bad Gateway** → L7. The upstream server returned an invalid response.
- **503 Service Unavailable** → L7. The application is overloaded or down.
- **Slow response** → Could be L7 (slow backend), L4 (congestion), or L1 (bad link).

Knowing the layer narrows the search. "It's a 502" → look at the application and upstream. "Connection timeout" → look at network, firewall, TCP.

### The TCP/IP Model: What's Actually Implemented

The OSI model is a teaching and debugging framework. The **TCP/IP model** (4 layers) is closer to reality:

| TCP/IP Layer | Maps to OSI | Contains |
|--------------|-------------|----------|
| **Application** | L5–L7 | HTTP, DNS, TLS, your code |
| **Transport** | L4 | TCP, UDP |
| **Internet** | L3 | IP, ICMP |
| **Link** | L1–L2 | Ethernet, WiFi, physical |

When you write an API, you work at the Application layer. When you debug a "connection refused," you're in Transport. When you configure BGP or routing, you're in Internet. The vocabulary crosses both models.

### Layer-by-Layer Debugging: Concrete Examples

**L1 (Physical)**: Link down, cable unplugged, WiFi interference. Symptom: no connectivity at all. Fix: check cables, restart NIC, move closer to router.

**L2 (Data Link)**: Wrong VLAN, MAC filtering, switch misconfiguration. Symptom: can't reach devices on same subnet. Fix: VLAN config, ARP table.

**L3 (Network)**: Wrong route, firewall block, BGP misconfig. Symptom: can reach some IPs, not others; traceroute shows where packets stop. Fix: routing table, firewall rules.

**L4 (Transport)**: Connection refused (nothing listening), connection timeout (firewall or overload), reset (server crashed). Symptom: `curl` hangs or "connection refused." Fix: ensure service is listening, check firewall, check server load.

**L7 (Application)**: 4xx/5xx status, malformed response, wrong Content-Type. Symptom: connection works but response is wrong. Fix: application logs, upstream health.

**Staff-Level Insight**: Start at L7 and work down. "We get 502" → L7. "We get connection timeout" → L4. "We can't reach the server at all" → L3 or below. Knowing where to look saves hours.

## ASCII Diagram: 7-Layer Stack with Examples

```
    YOUR REQUEST: "GET https://api.example.com/users"

    L7 Application    "GET /users"  HTTP request
            │
    L6 Presentation   TLS encrypt, JSON encode
            │
    L5 Session        "We have a session"
            │
    L4 Transport      TCP: reliable delivery, port 443
            │
    L3 Network        IP: route to 93.184.216.34
            │
    L2 Data Link      Ethernet: MAC addresses
            │
    L1 Physical      Light through fiber / radio waves
            │
            ═══════════  DATA TRAVELS  ═══════════
            │
    [Arrives at server, unwraps back up the stack]
```

---

# Part 2: TCP vs UDP

## The Transport Layer: Where Reliability Meets Speed

The transport layer (L4) is where we choose between **reliability** and **speed**. TCP gives you delivery guarantees: every byte arrives, in order, or the connection fails. UDP gives you none of that—but it's fast and simple. The choice ripples through your entire design. Use TCP for payments, file transfers, and APIs where correctness is non-negotiable. Use UDP (or UDP-based protocols like QUIC) for real-time media and games where a late packet is worse than a lost one. Staff engineers make this choice consciously, not by default.

## TCP: Reliable, Ordered, Connection-Oriented

**TCP (Transmission Control Protocol)** provides:

- **Reliability**: Acknowledgment (ACK) for each segment. Lost packets are retransmitted. No data loss (under normal conditions).
- **Ordering**: Packets may arrive out of order; TCP reassembles them in order before delivering to the application.
- **Connection-oriented**: A **three-way handshake** establishes the connection before any data flows.
- **Flow control**: Receiver tells sender how much it can accept. Prevents overwhelming the receiver.
- **Congestion control**: Sender slows down when the network is congested. Avoids collapse.

### The Three-Way Handshake

```
    CLIENT                                    SERVER
       |                                         |
       |  SYN (I want to connect)                |
       |---------------------------------------->|
       |                                         |
       |  SYN-ACK (OK, let's connect)            |
       |<----------------------------------------|
       |                                         |
       |  ACK (Great, starting now)              |
       |---------------------------------------->|
       |                                         |
       |  [Connection established. Data flows.]  |
       |<=======================================>|
```

**Cost**: 1.5 RTT (round-trip times) before the first byte of application data. For HTTPS, add TLS handshake: another 1–2 RTT. Total: ~2–3 RTT before your HTTP request even starts.

### TCP Overhead

- **Handshake**: 1.5 RTT before first data.
- **Head-of-line blocking**: If packet 3 is lost, packets 4, 5, 6 are held until 3 is retransmitted. One loss stalls the entire stream.
- **Retransmission**: Lost packet = wait for timeout or duplicate ACK, then resend. Adds latency.
- **Flow/congestion control**: Complexity. More state. More headers (20+ bytes minimum).

### When to Use TCP

- Web traffic (HTTP, HTTPS)
- Database connections (MySQL, Postgres)
- API calls where every byte must arrive
- File transfers
- Email (SMTP)
- Anything where **reliability and order** matter more than raw speed

## UDP: Unreliable, Unordered, Connectionless

**UDP (User Datagram Protocol)** provides:

- **Fire and forget**: Send a packet. No handshake. No ACK. No retransmission.
- **No ordering**: Packets may arrive out of order or not at all.
- **Connectionless**: No "connection" state. No handshake.
- **Minimal overhead**: 8-byte header vs TCP's 20+ bytes.

### When to Use UDP

- **Video streaming**: A dropped frame is acceptable. A 100 ms retransmit is not. Low latency wins.
- **Gaming**: Player position updates. Old position is useless; next packet has the new one. Speed over perfection.
- **Voice/VoIP**: A small glitch is better than lag. Real-time.
- **DNS queries**: Small request, small response. Often one packet each way. UDP is simpler.
- **Real-time analytics**: Some loss acceptable; low latency critical.

## Why HTTP/3 Uses QUIC (UDP-Based)

**HTTP/2** runs over TCP. One lost packet causes head-of-line blocking for the entire connection. Multiple streams multiplexed over one TCP connection all stall when one packet is lost.

**QUIC** (Quick UDP Internet Connections) runs over UDP. It implements its own reliability and ordering **per stream**. So:

- Stream A loses a packet → only Stream A waits for retransmission.
- Streams B, C, D continue.
- No head-of-line blocking across streams.

HTTP/3 is HTTP over QUIC. It avoids TCP's head-of-line blocking while still providing reliability where needed. That's why HTTP/3 can outperform HTTP/2 on lossy networks.

## ASCII Diagram: TCP vs UDP

```
    TCP: Reliable but slower                    UDP: Fast but unreliable

    CLIENT              SERVER                  CLIENT              SERVER
       |                   |                       |                   |
       | SYN               |                       | Data (no hello)    |
       |------------------>|                       |------------------>|
       | SYN-ACK           |                       | More data         |
       |<------------------|                       |------------------>|
       | ACK               |                       | (Maybe arrived.   |
       |------------------>|                       |  Maybe not.)       |
       |                   |                       |                   |
       | Data segment 1    |                       |                   |
       |------------------>|                       |                   |
       | ACK               |                       |                   |
       |<------------------|                       |                   |
       | (Lost segment 2)  |                       |                   |
       | ... timeout ...   |                       |                   |
       | Retransmit 2      |                       |                   |
       |------------------>|                       |                   |
       | (Stream stalled   |                       |                   |
       |  until 2 arrives) |                       |                   |
```

## L5 vs L6: TCP vs UDP

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Choice** | "We use TCP for our API" | "We use TCP because we need reliability. For real-time features we're evaluating QUIC/UDP" |
| **Latency** | "Requests are slow" | "TCP handshake + TLS = 2-3 RTT before first byte. For 50ms RTT that's 100-150ms. Connection reuse is critical" |
| **Head-of-line** | "Sometimes requests stall" | "TCP HoL blocking: one lost packet stalls the stream. HTTP/3/QUIC avoids this; consider for mobile/lossy networks" |

---

# Part 3: Sockets and Connections

## A Socket = IP Address + Port Number

A **socket** is an endpoint for communication. It's the combination of:

- **IP address**: Which machine (e.g., `93.184.216.34`)
- **Port number**: Which service on that machine (e.g., `443` for HTTPS)

So `93.184.216.34:443` is a socket. The client connects to that socket. The server listens on that socket.

One machine can have many ports. Port 80 = HTTP. Port 443 = HTTPS. Port 22 = SSH. Port 3306 = MySQL. Same IP, different "doors."

## Connection = Bidirectional Channel Between Two Sockets

A **connection** (in TCP) is a bidirectional channel between:

- **Client socket**: e.g., `192.168.1.10:54321` (client IP + ephemeral port)
- **Server socket**: e.g., `93.184.216.34:443` (server IP + service port)

The server creates a **listening socket**—it binds to a port and calls `listen()`. When a client calls `connect()`, the server accepts. A new **connection** is established. Each side can send and receive. When either side closes, the connection ends. The server's listening socket remains—ready for the next connection.

## File Descriptors and Limits

Each open connection uses a **file descriptor** (on Unix-like systems). Sockets are file descriptors. The kernel has limits:

- **Per-process**: `ulimit -n` (often 1024–65535)
- **System-wide**: `fs.file-max`

**65,536 ports** per IP address (0–65535). On the server, typically only one process listens per port. But each *connection* gets its own socket pair. So one server can handle many connections on port 443—each from a different client.

## Connection Overhead: Memory and Setup Cost

Each TCP connection consumes:

- **Kernel buffers**: Send and receive buffers (often 4–64 KB each per connection)
- **Connection state**: TCP state machine, sequence numbers, etc.
- **File descriptor**: One per connection

**100,000 connections** × ~100 KB buffer = **~10 GB** of kernel memory for buffers alone. Plus per-connection state. This is why the **C10K problem** (10,000 connections) was hard—and why **epoll** and event-driven I/O were necessary.

### Kernel and Application Limits: What Can Bite You

- **`ulimit -n`**: Max open file descriptors per process. Each socket = one FD. Default often 1024. For 10K connections, you need 10K+ FDs. Set `ulimit -n 65535` or higher.
- **`net.core.somaxconn`**: Max length of the listen queue. If `accept()` is slow, new connections queue here. Too small = connections refused under load.
- **`net.ipv4.tcp_max_syn_backlog`**: Half-open (SYN-received) connection backlog. Under SYN flood, this fills. Tune for your expected spike.
- **Ephemeral port exhaustion**: Client has 64K ports. With short `TIME_WAIT`, you can run out when opening many connections rapidly. Connection pooling reduces the need for new connections.

**Why This Matters at Scale**: At 1K QPS with a 60-second connection lifetime, you might have 60K simultaneous connections. Without tuning, you hit FD limits, listen backlog, or port exhaustion. Staff engineers know these knobs and set them proactively.

## Why Connection Pooling Exists

Creating a new TCP connection is expensive:

1. **DNS resolution** (if not cached): ~0–100 ms
2. **TCP handshake**: 1 RTT (~20–100 ms depending on distance)
3. **TLS handshake** (if HTTPS): 1–2 RTT
4. **Database auth** (if DB): additional round-trip

**Total**: 50–150 ms or more per new connection. For a single request that takes 5 ms to process, you're spending 10–30x the request time just on connection setup.

**Connection pooling**: Pre-create connections. Keep them open. Reuse. Grab one, use it, return it. Amortize the setup cost across many requests. **HikariCP** (Java) can hand out a connection in ~250 nanoseconds. Creating new: ~5–10 ms. That's 20,000–40,000x faster.

## Keep-Alive: Reuse Connections Across HTTP Requests

**HTTP/1.1** uses **Connection: keep-alive** by default. The TCP connection stays open after one request/response. The next request reuses it. No new TCP or TLS handshake.

Without keep-alive: each HTTP request = new TCP + TLS. With keep-alive: one handshake serves many requests.

**Staff-Level Insight**: Connection pooling (client → server) and keep-alive (HTTP) are two sides of the same idea: reuse connections. Don't pay the setup cost repeatedly.

## WebSocket: Upgrade to Persistent Bidirectional Connection

**WebSocket** starts as HTTP. Client sends `Upgrade: websocket`. Server agrees. The connection is "upgraded"—same TCP connection, but now bidirectional. Client and server can send frames at any time. No request/response pattern. Used for chat, real-time notifications, collaboration.

### Connection Pool Sizing: A Practical Guide

- **Database pool**: Start with `2 × cores` or `(DB max_connections / app instances)`. Monitor: (1) pool exhaustion (requests waiting); (2) database connection count. Too small = timeouts. Too large = DB overload.
- **HTTP client pool**: For outbound API calls, pool size should match concurrency. 100 concurrent requests to Service B = pool of ~100. Set timeouts (connect, read) to avoid leaks.
- **Connection leak**: If pool slowly drains to zero under load, you have a leak—connections not returned. Use `try/finally` or structured concurrency. Track "connections in use" vs "connections idle."

**Why This Matters at Scale**: A single mis-sized or leaky pool can take down an entire service. "Database connection limit reached" and "no connections available" are common production failures. Staff engineers design pools with limits, monitoring, and circuit breakers.

## The C10K/C100K/C1M Problem

| Era | Target | Solution |
|-----|--------|----------|
| **C10K** | 10,000 connections | Event-driven I/O (epoll, kqueue), non-blocking sockets |
| **C100K** | 100,000 connections | Kernel tuning, efficient event loops, reduced per-connection memory |
| **C1M** | 1,000,000 connections | Many-core, many-thread, or many-process; careful memory and buffer tuning |

The key: **one thread (or few threads) monitoring many file descriptors**. When any is ready (readable/writable), process it. Don't allocate one thread per connection.

## ASCII Diagram: Socket and Connection Lifecycle

```
    SERVER                              CLIENT

    socket() ──► create
    bind(port 443)
    listen()
         |
         |  [Listening socket: 0.0.0.0:443]
         |  [Waiting for connections...]
         |
         |                    connect(server:443)
         |<─────────────────────────────────────
         |
    accept() ──► new connection
         |
         |  [Connection: client_ip:54321 <-> server:443]
         |
         |  [Data flows both ways]
         |
         |  close()
         |<─────────────────────────────────────>
         |
    [Connection closed. Listening socket still open.]
```

---

# Part 4: HTTP — Methods, Status Codes, Headers

## HTTP Methods: What Action?

| Method | Purpose | Idempotent? | Safe? |
|--------|---------|-------------|-------|
| **GET** | Read, fetch | Yes | Yes |
| **POST** | Create | No | No |
| **PUT** | Replace entire resource | Yes | No |
| **PATCH** | Partial update | No* | No |
| **DELETE** | Remove | Yes | No |
| **HEAD** | Like GET, headers only | Yes | Yes |
| **OPTIONS** | What methods allowed? | Yes | Yes |

**Idempotent**: Doing it multiple times has the same effect as doing it once. GET /users/123 ten times = same result. DELETE /users/123 ten times = user deleted once.

**Safe**: No side effects. GET and HEAD don't change server state.

**Why idempotency matters for retries**: If a client retries a request (e.g., timeout, network glitch), an idempotent request is safe. Retrying POST might create a duplicate. Retrying PUT or DELETE is fine. Design your APIs with this in mind—use idempotency keys for POST if needed.

### Idempotency Keys for Non-Idempotent Operations

For **POST** (and non-idempotent PATCH), use **idempotency keys**: the client sends a unique key (e.g., UUID) in a header like `Idempotency-Key: abc-123`. The server stores the key with the result. If the same key is sent again (retry), the server returns the stored result instead of re-executing. This gives POST "effectively idempotent" behavior for retries. Payment APIs (Stripe) and critical write APIs use this pattern.

### Common HTTP Method Mistakes

| Mistake | Why It's Bad | Fix |
|---------|--------------|-----|
| GET for mutations | Crawlers, pre fetch, and redirects can trigger it. Data loss. | Use POST for create, PUT/PATCH for update |
| POST for reads | Not cacheable. Can't bookmark. Semantics wrong. | Use GET for reads |
| PUT without full resource | PUT implies replace. Partial update = PATCH | Use PATCH for partial updates |
| Overloading POST | "Action" endpoints like /doSomething. Hard to reason about. | Use proper methods; or use POST with clear action in path |

## HTTP Status Codes: The Server's Answer

| Range | Meaning | Examples |
|-------|---------|----------|
| **2xx** | Success | 200 OK, 201 Created, 204 No Content |
| **3xx** | Redirect | 301 Moved Permanently, 302 Found, 304 Not Modified |
| **4xx** | Client error | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests |
| **5xx** | Server error | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout |

### Key Status Codes

| Code | Meaning | When to Use |
|------|---------|-------------|
| **200 OK** | Success, body has data | GET, PUT, PATCH success |
| **201 Created** | Resource created | POST success, `Location` header often set |
| **204 No Content** | Success, no body | DELETE success, some updates |
| **301 Moved** | Permanent redirect | URL changed forever |
| **304 Not Modified** | Use cached copy | Conditional GET, cache valid |
| **400 Bad Request** | Malformed request | Invalid JSON, missing required field |
| **401 Unauthorized** | Not authenticated | Wrong/missing credentials |
| **403 Forbidden** | Authenticated but not allowed | Insufficient permissions |
| **404 Not Found** | Resource doesn't exist | Wrong ID, deleted resource |
| **429 Too Many Requests** | Rate limited | Client exceeded rate limit |
| **500 Internal Server Error** | Server bug | Uncaught exception, internal failure |
| **502 Bad Gateway** | Upstream returned invalid response | Proxy got garbage from backend |
| **503 Service Unavailable** | Overloaded or down | Server can't handle more, try later |
| **504 Gateway Timeout** | Upstream didn't respond in time | Proxy waited, upstream timed out |

**401 vs 403**: 401 = "Who are you?" (authentication failed). 403 = "I know who you are, but you can't do this" (authorization failed).

### Status Code Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| **200 for errors** | Client can't distinguish success from failure. Breaks retries, monitoring. | Use 4xx/5xx when request fails |
| **500 for client errors** | Misattributes cause. Metrics wrong. Client can't fix. | 400 for bad input, 401/403 for auth |
| **Generic 500** | No signal for retry vs don't-retry. Ops can't prioritize | Differentiate 503 (retry) vs 500 (bug) |
| **404 for "forbidden"** | Security through obscurity. Hides authorization bugs | 403 when auth'd but not allowed; 404 when resource missing |

**Staff-Level Insight**: Status codes are a contract. Clients (and proxies, CDNs) rely on them for retries, caching, and error handling. Wrong codes cause silent corruption (e.g., duplicate charges from retrying a "200" that didn't actually succeed) or broken UX (e.g., "Not found" when the user isn't logged in).

## HTTP Headers: Metadata That Matters

| Header | Direction | Purpose |
|--------|-----------|---------|
| **Content-Type** | Both | Format of body (e.g., `application/json`) |
| **Content-Length** | Both | Size of body in bytes |
| **Authorization** | Request | Credentials (e.g., `Bearer <token>`) |
| **Cache-Control** | Response | How to cache (`max-age=3600`, `no-cache`) |
| **Accept** | Request | What formats client accepts |
| **X-Request-ID** | Both | Trace request across services |
| **Cookie** / **Set-Cookie** | Request / Response | Session, auth state |
| **Location** | Response | Redirect target (with 3xx) |

**X-Request-ID** (or similar): Critical for distributed tracing. One ID from client, propagated through every service. When debugging, you search logs for that ID and see the full path.

### HTTP Headers for Production: What to Always Set

| Header | Set By | Value | Purpose |
|--------|--------|-------|---------|
| **X-Request-ID** | Client or first service | UUID | Distributed tracing; search logs by this |
| **X-Forwarded-For** | Proxy/LB | Client IP | Preserve real client IP behind proxies |
| **Cache-Control** | Server | `max-age=3600`, `no-store`, etc. | Control caching; critical for correctness |
| **Strict-Transport-Security** | Server | `max-age=31536000` | Force HTTPS; prevent downgrade attacks |
| **Content-Type** | Server | `application/json`, etc. | Client must know how to parse response |

Missing `X-Request-ID` makes debugging multi-service requests painful. Wrong `Cache-Control` can cause stale data or prevent caching of cacheable content. Staff engineers standardize on a small set of headers and ensure they're set consistently.

## REST Principles

- **Resource-based URLs**: `/users/123`, not `/getUser?id=123`. Nouns, not verbs.
- **HTTP methods as verbs**: GET = read, POST = create, PUT = replace, DELETE = remove.
- **Stateless**: Each request carries all needed context. No server-side session (or session in a store, not in app memory for scale).
- **Cacheable**: GET responses can be cached. Use `Cache-Control`, ETag, `If-None-Match`.
- **Uniform interface**: Same pattern for all resources. Predictable.

### REST Anti-Patterns and When to Break the Rules

| Anti-Pattern | Why People Do It | When It's OK | When It's Not |
|--------------|------------------|--------------|---------------|
| **POST for everything** | Simplicity, avoiding PUT/DELETE | Internal APIs, RPC-style | Public APIs, caching, semantics |
| **Actions in URL** | Feels natural | `/users/123/activate` as sub-resource | `/getUser`, `/deleteUser` |
| **Version in URL** | `/v1/users` | Common, clear | Consider header or content negotiation |
| **Over-nesting** | `/users/123/posts/456/comments/789` | Small depth | Deep nesting is hard to cache and reason about |

**Staff-Level Insight**: REST is a style, not law. Consistency within your API matters more than purity. If your org uses POST for reads internally, document it. But for public or partner APIs, following REST improves developer experience and tooling support.

## HTTP/1.1 vs HTTP/2 vs HTTP/3

| Version | Key Features |
|---------|--------------|
| **HTTP/1.1** | One request per connection (or pipelining, rarely used). Text-based. Headers repeated per request. |
| **HTTP/2** | Multiplexing: many requests over one connection. Binary. Header compression (HPACK). Server push. |
| **HTTP/3** | Same as HTTP/2 but over QUIC (UDP). No TCP head-of-line blocking. Better on lossy networks. |

**Multiplexing** (HTTP/2): One TCP connection carries many logical streams. Request A and B interleaved. No need for 6 connections to load 6 resources—one connection, 6 streams.

## HTTPS: TLS Adds Latency

**HTTPS** = HTTP over TLS. Before any HTTP data:

1. TCP handshake (1 RTT)
2. TLS handshake: ClientHello, ServerHello, certificate, key exchange (1–2 RTT)
3. Application data encrypted

**Total**: ~2–3 RTT before first byte of HTTP. Certificate exchange and key agreement add ~50–100 ms on a typical cross-country link. **TLS 1.3** reduces this to 1 RTT in many cases. Connection reuse (keep-alive) means you pay this once per connection, not per request.

### TLS Offload and Where to Terminate

**Terminate at load balancer**: The LB does TCP + TLS. Backend gets plain TCP. Pros: App servers don't do crypto. Cons: Traffic from LB to backend is unencrypted (often on private network). For compliance (PCI, HIPAA), you may need TLS to the backend too (TLS re-encryption).

**Terminate at application**: App server does TLS. End-to-end encryption. Pros: No plaintext on the wire. Cons: CPU on app servers for crypto. At scale, this can be significant.

**Mutual TLS (mTLS)**: Both client and server present certificates. Used for service-to-service auth in zero-trust networks. Adds complexity but strong security.

---

# Part 5: Bandwidth vs Latency

## Bandwidth: How Much Data per Second

**Bandwidth** is the capacity of the pipe—how much data can flow per second. Measured in **Mbps** (megabits per second) or **Gbps** (gigabits per second).

- Home connection: 100–1000 Mbps
- Datacenter link: 1–100 Gbps
- Cross-continent backbone: 100+ Gbps

**Higher bandwidth** = more data per second. Good for large transfers: video streaming, backups, bulk data sync.

## Latency: How Long Until First Byte

**Latency** (often **round-trip time**, RTT) is how long it takes for a packet to go from A to B and back. Measured in **milliseconds (ms)**.

| Scenario | Typical RTT |
|----------|-------------|
| Same datacenter | 0.1–0.5 ms |
| Same region (e.g., us-east) | 1–5 ms |
| Cross-continent (US–Europe) | 80–120 ms |
| US–Asia | 120–200 ms |
| Satellite | 500–700 ms |

**Lower latency** = faster response. Good for interactive: search, API calls, gaming, video calls.

## The Critical Distinction

- **Bandwidth** = pipe width. You can improve it (bigger links, more capacity).
- **Latency** = distance and physics. **Speed of light** is the floor. New York to Tokyo: light takes ~140 ms round-trip. No amount of money removes that.

For **small requests** (e.g., API call, search): latency dominates. The request and response are tiny. Bandwidth is rarely the limit. A 100 ms RTT means 100 ms before you see anything, regardless of bandwidth.

For **large transfers** (e.g., 1 GB file): bandwidth dominates. Latency is a one-time cost to start. Then throughput matters. 1 GB at 10 Mbps = 800 seconds. At 100 Mbps = 80 seconds.

### The Math: When Does Bandwidth Matter?

**Small request** (1 KB request, 2 KB response): 3 KB total. At 1 Mbps, transfer time = 3 KB / (1 Mbps / 8) ≈ 0.024 seconds. At 100 Mbps, 0.00024 seconds. The difference is negligible. RTT (50–200 ms) dominates. Bandwidth almost irrelevant.

**Large transfer** (1 GB): At 10 Mbps, 1 GB / (10/8 MB/s) ≈ 800 seconds. At 100 Mbps, ~80 seconds. Latency (even 200 ms) is negligible. Bandwidth is everything.

**Rule of thumb**: If your typical request/response is under ~100 KB and latency is under ~50 ms RTT, bandwidth is rarely the bottleneck. Optimize for latency (geography, connection reuse). For bulk data (video, backups, sync), optimize for bandwidth.

## Why This Matters at Scale

| Use Case | Dominant Factor | Mitigation |
|----------|-----------------|------------|
| Search, API | Latency | Geo-distributed servers, CDN edge |
| Video streaming | Bandwidth (after buffering) | CDN, adaptive bitrate |
| Real-time gaming | Latency | Regional game servers |
| Large file download | Bandwidth | Parallel connections, CDN |
| Video call | Latency | Low-latency codecs, regional PoPs |

## Geo-DNS and Anycast: Reduce Latency by Proximity

**Geo-DNS**: Resolve the same hostname to different IPs based on client location. Client in India gets an IP in Mumbai. Client in US gets an IP in Virginia. Same service, different edge.

**Anycast**: Same IP advertised from multiple locations. BGP routes the client to the **nearest** instance. One IP, many physical locations. Used by CDNs, DNS (e.g., 8.8.8.8), cloud LBs.

**Staff-Level Insight**: "Our p99 latency is 200 ms" often means "users far from our servers." Solution: put servers (or CDN edges) closer to users. Geo-DNS and Anycast are how you do that at scale.

## CDN: Cache at the Edge, Reduce Latency for Static Content

A **CDN (Content Delivery Network)** caches static (and sometimes dynamic) content at **edge locations**—close to users. Request for an image: if cached at edge, response comes from nearby PoP (20–50 ms). If not, request goes to origin (100+ ms). CDNs reduce latency and offload origin.

## ASCII Diagram: Bandwidth vs Latency

```
    BANDWIDTH (pipe width)              LATENCY (distance)

    [Client] ═══════════════ [Server]    [Client] ....RTT.... [Server]
              Wide pipe                      │
              More Mbps                     │
              Good for bulk                  │
              transfer                      │
                                            │  Time to first byte
                                            │  Physics-limited
                                            │  Good for interactive
                                            ▼

    Small request (1 KB):  Latency dominates.  RTT matters.
    Large transfer (1 GB): Bandwidth dominates. Mbps matters.
```

## Cross-Region Latency Map (Approximate)

```
    CROSS-REGION RTT (ms, approximate)

              Tokyo    Singapore   London   Virginia   California
    Tokyo       -        70         250      140        110
    Singapore  70        -         200      220        170
    London    250       200         -       80         140
    Virginia  140       220        80       -          70
    California 110      170       140      70          -

    Same region: 1-5 ms.  Cross-ocean: 70-250 ms.
    Speed of light limit: ~140 ms NY–Tokyo. Cannot improve without moving.
```

## L5 vs L6: Bandwidth and Latency

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Slow API** | "Need more bandwidth" | "For 1 KB responses, bandwidth isn't the issue. Check RTT. Are users far from servers? Add regions." |
| **CDN** | "We use CDN for static" | "CDN reduces latency for cache hits. For API, we need regional origins or edge compute." |
| **Geo** | "We have one region" | "p99 from Asia is 200 ms. Adding Tokyo region would cut to ~30 ms for Asia users." |
| **Capacity** | "Link is 10 Gbps" | "10 Gbps = 1.25 GB/s. For 10K QPS × 10 KB = 100 MB/s. We're fine. Latency is the bottleneck for small payloads." |

---

# Part 6: Debugging Network Issues — A Staff-Level Playbook

When requests fail or are slow, work through this checklist:

| Symptom | Check | Likely Cause |
|---------|-------|--------------|
| **Connection refused** | Is server listening? Firewall? | Port not open, firewall rule, wrong host |
| **Connection timeout** | TCP handshake completing? | Network path, firewall, server overload, SYN flood |
| **502 Bad Gateway** | What did upstream return? | Upstream crash, invalid response, timeout |
| **503 Service Unavailable** | Upstream health? Queue depth? | Overload, dependency down, circuit open |
| **504 Gateway Timeout** | Upstream response time? | Upstream slow, proxy timeout too short |
| **Intermittent failures** | Retry success? Pattern? | Transient network, partial outage, load balancer |
| **High latency** | Where is time spent? RTT? | Slow dependency, high RTT, serial calls |

**Tracing the full path**: Use **X-Request-ID** (or similar) from the client. Propagate through every service. When a request fails, search logs by that ID. You'll see: client → LB → gateway → service A → service B → DB. The slow or failing hop becomes obvious.

**Staff-Level Insight**: Network issues often manifest as "random" failures or "it works sometimes." The key is correlation: same user? same region? same service? Add tracing, metrics, and structured logging. The data will point you to the layer and the component.

---

# Part 7: A Complete Request Lifecycle — Tying It All Together

Consider a user in Tokyo loading a page from an API hosted in Virginia:

1. **DNS** (L7): Resolve `api.example.com`. Geo-DNS may return a Tokyo PoP IP. ~20–80 ms.
2. **TCP** (L4): SYN, SYN-ACK, ACK. 1 RTT. Tokyo–Virginia ~140 ms. So ~140 ms.
3. **TLS** (L6/L7): Handshake. 1–2 RTT. Another ~140–280 ms. (Or 0 if connection reused.)
4. **HTTP** (L7): GET request. ~1 ms on wire.
5. **Server** (L7): Process. May call DB in same region (low latency) or cross-region (high).
6. **HTTP Response** (L7): Body. ~few ms on wire.
7. **Browser**: Parse, render.

**Total for first request** (cold): 20 + 140 + 140 + 1 + 50 (server) + 2 ≈ **353 ms** minimum, before server work. Connection reuse: save 140 + 140 = 280 ms. **First byte** is dominated by RTT. **Time to load** depends on payload size and bandwidth for large responses.

**Why this matters**: For a 200 ms p99 target, you have almost no room for cross-ocean latency. You need regional deployment, edge caching, or accept higher latency for distant users. Staff engineers model this explicitly when setting SLAs and choosing regions.

---

# Part 8: Case Study — Debugging a Connection Exhaustion Incident

**Scenario**: Your service starts returning "No connections available" and 503s. The database is healthy. Other services are fine. What's happening?

**Step 1: Connection pool**. Is the pool exhausted? Metrics: "connections in use" vs "pool size." If "in use" equals "size" and stays there, every connection is busy. New requests block until one frees. Possible causes: (a) slow queries holding connections; (b) connection leak (connections not returned); (c) pool too small for load.

**Step 2: Connection leak**. If "in use" grows over time and never drops, you have a leak. Code path gets a connection, hits an exception, never returns it. Search for `getConnection` without matching `release`/`close` in a `finally` block. Or use a connection wrapper that auto-returns on close.

**Step 3: Downstream slowness**. If queries are slow, connections stay busy longer. Pool exhaustion is a symptom. Fix: optimize queries, add indexes, or scale the DB. Increase pool size only if the DB can handle more connections—otherwise you move the bottleneck.

**Step 4: File descriptor limits**. Each connection = one FD. Check `ulimit -n`. If you have 1K limit and 1K connections, you're at the cap. New connections fail. Increase limit or reduce connection count.

**Step 5: Database `max_connections`**. The DB has a limit. If your app opens 500 connections per instance and you have 10 instances, that's 5K connections. Postgres default might be 100. You'll hit the DB limit before the app. Use a connection pooler (pgBouncer) to multiplex.

**Resolution**: In one real incident, the cause was a new code path that caught an exception but didn't return the connection to the pool. Over 30 minutes, all 50 connections leaked. Fix: add `try/finally` to ensure return. Add pool metrics and alerting so you catch this before users see 503s.

---

# Example in Depth: One HTTPS Request — Where Time Goes (Tokyo → Virginia)

A user in **Tokyo** hits an API in **Virginia**. One GET, small payload. Where does the time go?

| Phase | What happens | Latency | Notes |
|-------|---------------|---------|--------|
| DNS | Resolve `api.example.com` (often cached) | 0–50 ms | Geo-DNS may return Virginia IP; resolver cache can make this 0 |
| TCP | SYN, SYN-ACK, ACK (1 RTT) | ~140 ms | Tokyo–Virginia RTT ~140 ms; unavoidable for first connection |
| TLS | Handshake (1–2 RTT) | ~140–280 ms | Session resume can reduce; first connection pays full cost |
| HTTP | GET request + response (1 RTT + serialization) | ~140 ms + few ms | Request and response each one RTT for small payloads |
| Server | Process request (DB, etc.) | 10–100 ms | Depends on app; may call DB in same region |

**First request (cold)**: 20 + 140 + 200 + 140 + 50 ≈ **550 ms** before body. **With connection reuse**: no TCP/TLS handshake next time → save ~340 ms; next request is ~20 + 140 + 50 ≈ **210 ms** (RTT + server). So **connection reuse and keep-alive** are critical for cross-region APIs. Staff engineers: put APIs in regions close to users, or use edge/regional replicas; for cross-region, minimize round-trips (batch, avoid N+1) and always reuse connections.

## Breadth: Network Failure Modes and API Design Edge Cases

| Failure / scenario | Layer | Symptom | Mitigation |
|--------------------|-------|---------|------------|
| Connection refused | L4 (TCP) | No server listening or firewall | Check process, port, firewall rules; health checks |
| Timeout (connect or read) | L4/L7 | Slow or unreachable peer | Set timeouts; retry with backoff; circuit breaker |
| 502 Bad Gateway | L7 | LB got invalid response from upstream | Fix upstream crash/timeout; validate LB health checks |
| 503 Service Unavailable | L7 | Upstream overloaded or down | Scale; circuit breaker; retry with backoff |
| TLS handshake failure | L6 | Certificate, version, or cipher mismatch | Align client/server TLS config; monitor cert expiry |
| Connection exhaustion | L4 / app | No free connections in pool | Pool size, timeouts, connection reuse; check for leaks |

**Edge cases**: **Retries**: Retry only on 5xx and 429; not on 4xx (except 429 with backoff). **Idempotency**: POST/PUT/DELETE must be safe to retry—use idempotency keys. **Request IDs**: Send `X-Request-ID`; log and return in response for debugging. **Large responses**: Stream or paginate; avoid single 100 MB JSON. **Slow clients**: Set write timeouts so a slow client doesn't hold a thread and connection forever.

---

# Appendix: Quick Reference — Networking for System Design

## TCP vs UDP Decision Tree

- **Need every byte?** (file transfer, API, DB) → TCP
- **Real-time, some loss OK?** (video, gaming, VoIP) → UDP
- **Web, need multiplexing + reliability?** → HTTP/2 (TCP) or HTTP/3 (QUIC/UDP)

## Status Code Cheat Sheet

| Range | Meaning | Retry? |
|-------|---------|--------|
| 2xx | Success | No |
| 3xx | Redirect | Follow Location |
| 4xx | Client error | No (fix request) |
| 429 | Rate limited | Yes, with backoff |
| 5xx | Server error | Yes (except 501) |
| 502, 503, 504 | Gateway/upstream issues | Yes, with backoff |

## Key Headers for APIs

| Header | Direction | Purpose |
|--------|-----------|---------|
| Authorization | Request | Auth token |
| Content-Type | Both | Request/response format |
| X-Request-ID | Request | Tracing |
| Cache-Control | Response | Caching behavior |
| Idempotency-Key | Request | Safe retries for POST |

## Latency Budget (Typical)

| Hop | Latency |
|-----|---------|
| Same datacenter | 0.1–1 ms |
| Same region | 1–5 ms |
| Cross-region | 50–150 ms |
| Cross-continent | 100–250 ms |
| TCP + TLS handshake | 1–3 RTT |

## Staff-Level Networking Questions

1. "Which layer is this failure?" (L4 vs L7 narrows the search)
2. "Are we reusing connections?" (pool, keep-alive)
3. "What's our RTT to users?" (drives regional deployment)
4. "Do we have request IDs for tracing?"
5. "Are our status codes correct for retries and monitoring?"

---

# Summary: From Fundamentals to Staff-Level Networking

Networking fundamentals underpin every distributed system. Staff engineers:

1. **Diagnose by layer**: Connection refused (L4). 502 (L7). Timeout (L4/L3). Know where to look.
2. **Choose TCP vs UDP appropriately**: Reliability vs speed. QUIC/HTTP/3 when head-of-line blocking hurts.
3. **Reuse connections**: Connection pooling, keep-alive. Never pay handshake cost per request.
4. **Design HTTP APIs with care**: Idempotency for retries. Correct status codes. Request IDs for tracing.
5. **Distinguish bandwidth from latency**: Small requests = latency. Large transfers = bandwidth. Optimize the right one.
6. **Put servers close to users**: Geo-DNS, Anycast, CDN, regional deployment. Physics is the limit.

When you design a system, ask: What's the request path? Where are the connections? What's the RTT? What fails and at which layer? The answers will shape your architecture—and your ability to debug it when things break.
