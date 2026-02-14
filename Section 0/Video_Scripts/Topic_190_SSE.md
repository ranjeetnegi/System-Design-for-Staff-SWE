# Server-Sent Events (SSE): One-Way Push

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A radio station. You tune in. The station broadcasts. You listen. You can't talk back to the station. One-way flow: server to client. SSE works exactly like this. The server pushes events to the client over HTTP. Simple. Built-in reconnection. No WebSocket complexity. Perfect for live feeds, stock prices, notifications, dashboards.

---

## The Story

Server-Sent Events (SSE) is a standard for one-way server-to-client push over HTTP. Client opens a connection. Server keeps it open. When the server has data, it sends it. Event format: "data: something\n\n" (or structured). Client receives. Connection stays open. Server sends more. And more. No client request per message. Push. Simple.

Built-in reconnection: if the connection drops, the browser's EventSource automatically reconnects. Sends "Last-Event-ID" header so the server can resume. You don't code reconnection. The browser does it. Huge for reliability.

Limitation: one-way. Server → client only. Client can't send data over the SSE connection. For client→server, use a normal HTTP request. Many apps need that anyway: "subscribe" (HTTP POST), then receive stream (SSE). Clean separation.

---

## Another Way to See It

Think of a news ticker in a building lobby. Text scrolls. You watch. You don't send anything back to the ticker. It pushes. You receive. SSE is that ticker. Server has the news. Pushes. Client displays. One direction. Simple.

Or a sports scoreboard. Scores update. Fans watch. No interaction. Push model. SSE fits that mental model perfectly.

---

## Connecting to Software

Technically: HTTP response with "Content-Type: text/event-stream." Connection: keep-alive. Format: lines of text. "data: {json}\n\n" (double newline = message boundary). Or "event: customEvent\ndata: ...\n\n" for named events. Client uses EventSource API: `new EventSource('/stream')`. On message: handler runs. Automatic reconnect on disconnect.

Server side: any language. Node: express with a stream. Python: Flask with generator. Go: flush after each write. Key: don't buffer. Flush immediately so client gets data in real time. Proxies: some buffer. Disable buffering for event-stream. Nginx: `proxy_buffering off` for SSE paths.

---

## Let's Walk Through the Diagram

```
    SSE: ONE-WAY PUSH

    Client                              Server
       │                                   │
       │──── GET /stream ─────────────────►│
       │                                   │
       │◄─── 200, Content-Type: ──────────│
       │     text/event-stream             │
       │                                   │
       │◄─── data: {"price": 100} ─────────│  (flush)
       │                                   │
       │◄─── data: {"price": 101} ─────────│  (flush)
       │                                   │
       │◄─── data: {"price": 102} ─────────│  (flush)
       │                                   │
    Client receives. Connection stays open. Server pushes when ready.
    Client never sends over this connection.
```

---

## Real-World Examples (2-3)

**Example 1: ChatGPT (streaming).** When you send a prompt, the response streams token by token. That's often SSE (or similar). Server pushes. Client displays as it arrives. One-way. Perfect fit. No need for client to send mid-stream over the same connection.

**Example 2: Stock trading dashboard.** Real-time prices. SSE from server. Client displays. Updates flow. No polling. Low latency. One-way is enough—client sends orders via separate API. Clean.

**Example 3: Build system (e.g., GitHub Actions).** Logs stream as the job runs. SSE or similar. Server pushes log lines. Client shows them live. You watch. One-way. Simple.

---

## Let's Think Together

**When use SSE instead of WebSocket?**

When you only need server→client push. Notifications. Live feeds. Dashboards. Status updates. SSE is simpler. Native browser API. Auto-reconnect. No need for Socket.io or similar. WebSocket adds complexity for bidirectional. If you don't need client→server on the same channel, SSE wins. Use HTTP for client→server (form submit, API call). SSE for server→client stream.

**How does SSE handle reconnection?**

Browser sends "Last-Event-ID" header with the last received event ID (if you send "id: 123" in your events). Server can resume from that point. Send missed events. Or send "here's the current state" and continue. Depends on your use case. Key: reconnect is automatic. You design the resume logic.

**When is SSE a bad fit?**

When you need client→server on the same channel. Chat apps need both directions—use WebSocket. When you need binary data—SSE is text. Base64 encode if you must, but WebSocket handles binary natively. When connection count is huge—each SSE connection is a long-lived HTTP connection. Thousands of clients = thousands of connections. Plan your server capacity. For moderate scale and one-way push, SSE shines.

**Event types:** You can send named events. "event: priceUpdate\ndata: {...}\n\n". Client listens for specific event types. Multiple handlers. Or use "event: " for default. Flexible. Good for multiplexing different update types over one connection. Stock prices, order status, notifications—all over one SSE stream. One connection, many event types.

**Performance:** One SSE connection per client. Lightweight. Compare to polling: 100 clients, 10-second poll = 10 req/sec. SSE: 100 connections, push when needed. Far fewer total requests when updates are infrequent. Server pushes only when there's data. Efficient. Scales well for moderate connection counts with infrequent updates. Connection pooling: each browser has limits (6 per domain for HTTP/1.1). SSE uses one. Plan for it when you have many streams. HTTP/2 multiplexing helps. SSE is often the sweet spot for server push: simpler than WebSocket, more efficient than polling. Consider it first for one-way streams. Upgrade to WebSocket only when you need bidirectional flow. Many use cases—dashboards, feeds, notifications—work perfectly with SSE. Simplicity wins when it fits.

---

## What Could Go Wrong? (Mini Disaster Story)

A company uses SSE for a live dashboard. Works locally. Deploy behind Nginx. Nginx buffers responses by default. Client receives nothing until buffer fills or connection ends. Dashboard shows stale data. They add `proxy_buffering off` for the SSE path. Flush on every write. Works. Lesson: proxies and load balancers often buffer. SSE needs immediate flush. Configure your infrastructure.

---

## Surprising Truth / Fun Fact

SSE is part of the HTML5 spec. EventSource API. Supported in all modern browsers. IE? No. But that's legacy. For modern web, it's native. No library. `new EventSource(url)`, `evtSource.onmessage = (e) => ...`. Done. Underused. Many reach for WebSocket when SSE would suffice. Simpler is better when it fits.

---

## Quick Recap (5 bullets)

- **SSE** = server pushes events to client over HTTP. One-way. Server → client only.
- Simple: Content-Type text/event-stream, send "data: ...\n\n". Client uses EventSource.
- Built-in reconnection. Browser handles it. Last-Event-ID for resume. Reliability out of the box.
- Use for: live feeds, notifications, dashboards, stock prices, streaming responses. One-way push.
- Simpler than WebSocket when you don't need bidirectional. Configure proxies to not buffer.

---

## One-Liner to Remember

SSE = radio station. You tune in. Server broadcasts. You listen. You can't talk back. Simple. Built-in reconnect. Perfect for one-way push.

---

## Next Video

Next up: **Cursor-Based Pagination vs Offset**—the train conductor. Count from the beginning? Or jump directly to "after this carriage"?
