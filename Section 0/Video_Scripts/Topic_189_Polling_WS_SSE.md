# Long Polling vs WebSocket vs SSE

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Three ways to get breaking news. Way 1, short polling: call the news desk every 5 minutes. "Any news?" "No." Call again. "Any news?" "No." Wasteful. Way 2, long polling: call, stay on the line. "I'll wait." When news happens, they tell you immediately. Then you call again. Way 3, WebSocket: open a dedicated hotline. News flows instantly, both ways. Way 4, SSE: subscribe to a one-way radio channel. News pushes to you. You can't talk back. Each has a trade-off.

---

## The Story

**Short polling**: client requests on a fixed interval. Every 5 seconds, every 10 seconds. "Any updates?" Server responds immediately—data or empty. Simple. But wasteful. 99% of requests return "nothing new." Wasted bandwidth. Wasted CPU. Latency = up to one full interval. Update happens at second 1? Client might not know until second 10. Fine for "good enough" scenarios. Bad for real-time.

**Long polling**: client requests. Server holds the connection until there's data. Or until timeout (e.g., 30 seconds). When data arrives, server responds. Client immediately sends a new request. Better. Fewer empty responses. Lower latency—client gets data as soon as it exists. But: each "message" still requires a new HTTP request. Connection churn. Some firewalls timeout long-held connections.

**WebSocket**: one persistent connection. Full-duplex. Client sends anytime. Server sends anytime. No polling. Lowest latency. Most efficient for high-frequency, bidirectional. Overhead: connection setup. Complexity: stateful servers, scaling. Best for chat, gaming, collaborative apps.

**SSE (Server-Sent Events)**: one-way. Server pushes to client. Client can't send over the same channel (uses normal HTTP for that). Simpler than WebSocket. Built-in reconnection. Text-based. Perfect for: live feeds, notifications, dashboards. When you only need server→client push. Easier than WebSocket. Less powerful.

**Summary table:** Short poll = simple, wasteful. Long poll = better latency, good fallback. WebSocket = full-duplex, lowest latency, most complex. SSE = one-way push, simpler than WebSocket. Match the approach to your needs. Don't default to WebSocket when SSE or long poll would do.

**Socket.io and fallbacks:** Libraries like Socket.io try WebSocket first. If it fails (proxy, corporate firewall), fall back to long polling. Best of both. Use when you need reliability across diverse networks. Not every environment allows WebSocket. Fallback is a safety net.

**Choosing:** List your requirements. One-way or two-way? Low latency critical? Simple implementation? That narrows it. One-way + simple → SSE. Two-way + low latency → WebSocket. Can't use WebSocket → long polling. Minimal dev, "good enough" → short polling. Decision tree. Match tool to need.

---

## Another Way to See It

Think of checking your mailbox. Short polling: walk to mailbox every hour. Usually empty. Long polling: sit by the mailbox. Mailman arrives, you get it. Then you sit again. WebSocket: mailman has a direct line to your hand. Delivers the moment he has something. Both ways—you can hand him letters too. SSE: mailman pushes to you. You can't push back on that channel. One-way delivery.

---

## Connecting to Software

| Approach      | Direction     | Latency      | Complexity | Use Case                    |
|---------------|---------------|--------------|------------|-----------------------------|
| Short polling | Client→Server | High         | Low        | Simple, low-frequency       |
| Long polling  | Client→Server | Medium       | Medium     | When WebSocket overkill     |
| WebSocket     | Both          | Low          | High       | Chat, gaming, bidirectional |
| SSE           | Server→Client | Low          | Low        | Feeds, notifications        |

Choose by need. One-way push? SSE. Two-way? WebSocket. Can't use WebSocket (old proxy, simple need)? Long polling. "Good enough" and minimal dev? Short polling.

---

## Let's Walk Through the Diagram

```
    SHORT POLLING              LONG POLLING           WEBSOCKET / SSE

    C ──?──► S  "no"           C ──?──► S (waits)     C ═══════► S
    C ──?──► S  "no"                ...                    (one connection)
    C ──?──► S  "no"                S ──data──► C          S ──data──► C
    C ──?──► S  "data!"             C ──?──► S (waits)     S ──data──► C
                                         ...               (instant, both ways
    Wastes requests.                 Fewer requests.       or one-way for SSE)
    Latency = interval               Better latency
```

---

## Real-World Examples (2-3)

**Example 1: Twitter timeline.** Early Twitter used long polling. "Give me new tweets." Server held until new tweets or timeout. Simpler than WebSocket. Good enough for timeline updates. Later they moved to more sophisticated infrastructure.

**Example 2: Slack.** WebSocket for the main message stream. Bidirectional. Send message, receive messages. Real-time. Typing indicators. Perfect fit.

**Example 3: Stock dashboard.** SSE. Server pushes price updates. Client displays. One-way. No need for client to send over that channel. Simpler than WebSocket. Built-in reconnect. Ideal.

---

## Let's Think Together

**When would you use long polling instead of WebSocket?**

When WebSocket is problematic. Corporate proxy that blocks WebSocket. Legacy environment. Or: simple need, don't want WebSocket complexity. One-way updates, low frequency. Long polling is "good enough." Also: fallback. Try WebSocket. Fail? Fall back to long polling. Socket.io does this. Best of both.

**SSE vs WebSocket for one-way push?**

SSE is simpler. Native browser support. Automatic reconnect. Text only. WebSocket does bidirectional, binary. If you only need server→client, SSE is often the better choice. Less code. Less to debug. Use WebSocket when you need client→server on the same channel.

---

## What Could Go Wrong? (Mini Disaster Story)

A team uses short polling for a live auction. "Get current bid" every 2 seconds. 10,000 users. 5,000 requests per second to the server. Server overloads. Bids lag. Users see stale prices. Last-minute bids fail. They switch to WebSocket. One connection per user. Server pushes updates. 10,000 connections, but far fewer requests. Server breathes. Lesson: polling doesn't scale for high-frequency, many-users scenarios. Push is better.

---

## Surprising Truth / Fun Fact

SSE is simpler than WebSocket but lesser known. It's just HTTP. "Content-Type: text/event-stream." Keep connection open. Send lines of text. Browser's EventSource API handles reconnect automatically. No library needed. Redis uses it for pub/sub notifications. Many internal tools use it. Underrated for one-way push.

---

## Quick Recap (5 bullets)

- **Short polling**: request at intervals. Simple but wasteful. High latency.
- **Long polling**: request, server holds until data. Fewer requests. Better latency. Good fallback.
- **WebSocket**: persistent, full-duplex. Lowest latency. Best for bidirectional real-time.
- **SSE**: server pushes to client. One-way. Simpler than WebSocket. Great for feeds, notifications.
- Choose by direction (one-way vs two-way), latency needs, and complexity tolerance.

---

## One-Liner to Remember

Short poll = call repeatedly. Long poll = stay on the line. WebSocket = open hotline, both talk. SSE = one-way radio. Pick the channel that fits.

---

## Next Video

Next up: **Server-Sent Events (SSE)**—the radio station. You tune in. The station broadcasts. You listen. You can't talk back. Simple. Effective.
