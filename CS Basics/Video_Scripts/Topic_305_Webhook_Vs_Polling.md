# Webhook vs Polling

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're waiting for a package. Polling: you walk to the door every five minutes. "Is it here? No. Is it here? No. Is it here? Yes!" Twenty trips. One package. Wasteful. Webhook: the delivery person rings your doorbell when it arrives. You don't check. You get notified. One event. No waste. That's the difference. Push versus pull. Which one should you use?

## The Story

**Polling** means the client repeatedly asks the server: "Any updates?" Every 5 seconds. Every minute. Whatever you set. Simple. The client controls the timing. No need for the server to know where to send stuff. No need for the client to expose an endpoint. Firewall-friendly. Works from behind NAT. Works from a mobile device. But here's the cost: most of those requests return "nothing new." Ninety-nine percent of polls might be empty. Wasted bandwidth, wasted CPU. And if something happens *between* polls—say at second 3 of a 30-second interval—you don't see it until second 30. Delayed. If 1000 clients poll every 5 seconds, that's 200 requests per second—often for no data. Scales poorly. The server does a lot of work for mostly nothing.

**Webhook** means the server pushes to the client when something happens. Payment succeeded? Server sends a POST to your URL. New order? POST. Efficient. Real-time. One event, one request. No wasted polling. But: the client must expose a public URL that the server can reach. The server must retry if the client is down—with exponential backoff. Ordering isn't guaranteed—you might get event B before event A if A failed and retried. And firewalls sometimes block incoming connections—corporate networks, some cloud environments. Webhooks assume the client is reachable. That's not always true.

## Another Way to See It

Polling is like refreshing your email every minute. You're doing the work. You're in control of when you check. Webhook is like getting a push notification. The server does the work. You get notified when it matters. One is pull. One is push. Different trade-offs. There's also long polling: you open a request, the server holds it open until there's new data, then responds. You immediately open another. It's a hybrid—client-initiated, but server-push when data arrives. Used by some chat systems and real-time feeds.

## Connecting to Software

Polling: `GET /orders?since=last_check`. Client stores `last_check`, calls again in 60 seconds. Simple loop. Works everywhere. No special setup. Webhook: you give Stripe a URL. `https://yoursite.com/webhooks/stripe`. Stripe POSTs to it when a payment completes. Your server must be up. Must respond 200 quickly—within seconds—or Stripe retries. Must process async: enqueue the work, return 200, process in background. Stripe will retry with exponential backoff if you don't respond 200. You must handle duplicates—use the event ID as an idempotency key. Same event ID, process once.

## Let's Walk Through the Diagram

```
POLLING:
  Client                    Server
    | --- GET /updates?t=0 --->  (nothing)
    | <--- [] -------------------|
    | --- GET /updates?t=60 ---> (nothing)
    | <--- [] -------------------|
    | --- GET /updates?t=120 ---> (event happened at t=95!)
    | <--- [event] --------------|
  (You missed 25 seconds of delay)

WEBHOOK:
  Client                    Server
    | (listening)              |
    | <--- POST /webhook -------|  (event at t=95)
    | --- 200 OK -------------->|
  (Instant. One request.)
```

## Real-World Examples (2-3)

- **Stripe payments**: Webhooks. You can't poll "is payment done?" efficiently. Stripe pushes. You process.
- **GitHub Actions**: Webhook when you push. No polling. Real-time.
- **Health checks**: Polling. "Is the server up?" Simple. No need for push.
- **Stock prices on a dashboard**: Could be either. Polling every 30 sec is fine for casual view. WebSocket or webhook for trading—latency matters there. Or long polling: client opens a request, server holds it until there's new data, then responds. Client immediately opens another. Hybrid approach.
- **CI/CD pipelines**: Webhooks. Push to GitHub? Webhook fires. Build starts. No polling. Efficient. Same for Slack notifications, Jira updates, deployment pipelines. Event-driven. Push when it happens.

## Let's Think Together

**Stripe sends a webhook: "payment succeeded." Your server is down for 5 minutes. What happens to the webhook?**

Stripe tries to deliver. Your server returns 5xx or doesn't respond. Stripe retries. Exponential backoff: 1 min, 5 min, 30 min, 2 hours... For days. When your server comes back, you might get the same webhook multiple times. You must handle duplicates—use the event ID as an idempotency key. Never assume "one event, one delivery." Design for at-least-once, deduplicate on your side. And respond 200 quickly. If you start processing and take 30 seconds, Stripe times out and retries. You'll process twice. Better: accept the webhook, enqueue to a job, return 200 in under 5 seconds. Process async. Idempotently.

## What Could Go Wrong? (Mini Disaster Story)

You build a webhook receiver. Payment completed? You ship the order. But your server is slow. You take 30 seconds to process. Stripe's timeout is 10 seconds. Stripe retries. You get the webhook twice. You ship the order twice. Customer gets double merchandise. You lose money. Fix: respond 200 immediately. Queue the work. Process async. And use idempotency—same event ID, process once.

## Surprising Truth / Fun Fact

Webhooks have been around since the early 2000s. GitHub popularized them in 2008. "Notify me when someone pushes." Before that, everyone polled. Now webhooks are standard for payments, CI/CD, and event-driven systems. Stripe, Twilio, Slack—all push. But polling isn't dead. Sometimes it's the right choice—when the client can't expose an endpoint, when events are rare, when simplicity wins. Long polling—where the server holds the request until there's data—is a hybrid. Know your options. Use the right one.

---

## Quick Recap (5 bullets)

- Polling: client repeatedly asks "any updates?"—simple, client-controlled, but wasteful and delayed
- Webhook: server pushes when something happens—efficient, real-time, but client needs public URL
- Use polling when: simple integration, client can't expose endpoints, firewalls block incoming
- Use webhook when: real-time matters, high event frequency, you want to save resources—one event, one push, no wasted polls
- Webhooks can arrive more than once—design for idempotency and quick 200 response; process async, not inline

## One-Liner to Remember

*Polling: you ask. Webhook: they tell you.*

When the client can't receive push (firewall, mobile background limits), polling wins. When real-time and efficiency matter, webhook wins. Choose based on your constraints. Many systems use both: webhook for critical events (payments), polling as a fallback or for low-frequency checks. Hybrid is fine. The right answer is the one that fits your architecture and client capabilities.

---

## Next Video

Up next: Idempotency keys—how to stop that double-click from charging twice. See you there.
