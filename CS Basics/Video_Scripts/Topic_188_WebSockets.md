# WebSockets: When to Use for Real-Time

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Normal HTTP is like a walkie-talkie. You press a button to talk. Release to listen. One side at a time. Clunky. WebSocket is like a phone call. Both sides talk whenever they want. Continuous. Full-duplex. No "press to talk." Once the connection is open, data flows freely in both directions. Chat. Live scores. Stock tickers. Collaborative editing. Gaming. That's WebSocket.

---

## The Story

HTTP is request-response. Client asks. Server answers. Connection closes. Need more data? New request. Over and over. For real-time—data flowing continuously—HTTP is awkward. Polling: client keeps asking "any updates?" Wasteful. Lots of empty responses. Long polling: better. Client asks, server holds until there's data. Still: each "message" requires a new request. Overhead. Latency.

WebSocket: one connection. Upgraded from HTTP (HTTP handshake, then "Upgrade: websocket"). After that, it's a bidirectional pipe. Client sends. Server sends. Anytime. No request envelope. Just frames. Low latency. Efficient. Perfect for real-time.

Use cases: chat (messages both ways), live scores (server pushes updates), stock tickers (prices stream), collaborative editing (cursor positions, edits), gaming (player moves, game state), notifications (server pushes). Anything where the server needs to push without the client asking first. WebSocket excels.

---

## Another Way to See It

Think of a highway vs a driveway. HTTP: you drive to a store (request), get your items (response), go home. Repeat. Each trip is separate. WebSocket: the highway is open. You drive when you want. Trucks deliver when they want. Two-way traffic. Continuous. That's WebSocket—the open highway for data.

Or a water pipe. HTTP: you turn on the tap, get water, turn off. Each time. WebSocket: pipe is open. Water flows both ways when needed. No turn-on, turn-off for every drop.

---

## Connecting to Software

Technically: client sends HTTP request with "Upgrade: websocket." Server responds 101 Switching Protocols. Now it's WebSocket. Binary or text frames. Ping/pong for keepalive. Close frame to terminate. All over TCP. Same port as HTTP (80/443). Proxies and load balancers must support it—some don't. Check.

Servers: Socket.io (Node), Django Channels, Spring WebSocket. Clients: browser has native WebSocket API. `new WebSocket(url)`. Or Socket.io client for reconnection, fallbacks. Deployment: stickiness matters. Connection is stateful. Load balancer must route same client to same server. Or use a shared pub/sub (Redis) so any server can broadcast.

**Connection lifecycle:** Open, data flows, close. Handle reconnection on the client. Server restarts? Clients reconnect. Network blip? Reconnect. Idempotency: if a message might be sent twice after reconnect, design for it. "Message delivered" is not always "message processed once." Idempotency keys help for critical flows.

**Heartbeats and timeouts:** Long-lived connections can go stale. Client disconnected but didn't send close? Server holds the connection. Use ping/pong or application-level heartbeats. No traffic for N minutes? Close. Free resources. Client reconnects. Design for connection churn. It will happen.

**Frame types:** WebSocket has text and binary frames. Use binary for efficiency when possible (images, protobuf). Text for JSON, human-readable. Both work. Choose based on payload. Compression (per-message deflate) can reduce bandwidth. Enable if your library supports it. Matters at scale. Subprotocols: WebSocket supports subprotocol negotiation. Client and server agree on format (e.g., wss:// for binary protocol). Useful for custom protocols over WebSocket. WebSocket is the foundation for real-time web. Learn it. Use it when the use case fits. Don't force it where HTTP or SSE would suffice.

---

## Let's Walk Through the Diagram

```
    HTTP (Request-Response)                    WEBSOCKET (Full-Duplex)

    Client                    Server           Client                    Server
      │                         │                 │                         │
      │──── Request ───────────►│                 │═══ Upgrade (HTTP) ═════►│
      │                         │                 │◄══ 101 Switching ─══════│
      │◄───── Response ─────────│                 │                         │
      │                         │                 │═══ Frame ──────────────►│
      │──── Request ───────────►│                 │◄══ Frame ───────────────│
      │◄───── Response ─────────│                 │◄══ Frame ───────────────│
      │                         │                 │═══ Frame ──────────────►│
    Each message = new request                  One connection. Both can send anytime.
```

---

## Real-World Examples (2-3)

**Example 1: Slack.** Real-time messaging. WebSocket (or similar) for the message stream. Type, see others typing. Messages appear instantly. No polling. Full-duplex. Core to their UX.

**Example 2: Robinhood.** Live stock prices. WebSocket stream. Prices update in real time. No refresh. No 5-second polling. Push when price changes. Latency matters for trading UI.

**Example 3: Google Docs.** Collaborative editing. Cursor positions, edits flow both ways. WebSocket (or operational transform over WebSocket). Multiple users, same doc, real-time sync. WebSocket makes it possible.

---

## Let's Think Together

**When should you NOT use WebSocket?**

When request-response is enough. CRUD API. Form submit. Image upload. HTTP is simpler. When you need one-way server push only—SSE might be simpler. When connections are short-lived—HTTP overhead is one-time. WebSocket overhead is connection setup. For many quick, independent requests, HTTP can be better. Use WebSocket when you need persistent, bidirectional, real-time flow.

**How do you scale WebSocket connections?**

Each connection is stateful. 10,000 users = 10,000 connections. One server can't hold millions. Horizontal scaling: multiple servers. Sticky sessions so a client stays with one server. Or: use a message broker (Redis Pub/Sub). Server A receives message, publishes to channel. All servers subscribed. Each sends to its connected clients. Broadcast works across servers.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds a chat app. WebSocket. One server. Works great. Grows to 50,000 concurrent users. One server. Connections pile up. Memory explodes. Server crashes. They add more servers. Load balancer. But no stickiness. User connects to Server A. Friend connects to Server B. Message from A to B? Lost. They didn't design for multi-server. Had to add Redis Pub/Sub. Lesson: plan for horizontal scaling from day one. WebSocket doesn't scale on one box forever.

---

## Surprising Truth / Fun Fact

WebSocket was standardized in 2011 (RFC 6455). Before that, people used Flash sockets, long polling, Comet. WebSocket made it native to the browser. No plugin. One API. Game changer for real-time web apps. Now ubiquitous. Even some APIs (e.g., Binance) offer WebSocket for high-frequency trading data.

---

## Quick Recap (5 bullets)

- **WebSocket** = persistent, full-duplex connection. Both client and server can send anytime. No request-response.
- Use for: chat, live feeds, stock tickers, collaborative editing, gaming, push notifications.
- Starts as HTTP upgrade. Then binary/text frames. Same port as HTTP. Proxies must support it.
- Stateful: need sticky sessions for load balancing. Use pub/sub (Redis) for multi-server broadcast.
- Don't use when HTTP request-response suffices. WebSocket adds complexity. Use when you need real-time, bidirectional flow.

---

## One-Liner to Remember

WebSocket = phone call, not walkie-talkie. Both sides talk whenever they want. One connection. Full-duplex. Real-time.

---

## Next Video

Next up: **Long Polling vs WebSocket vs SSE**—three ways to get breaking news. Call every 5 minutes? Stay on the line? Or open a hotline?
