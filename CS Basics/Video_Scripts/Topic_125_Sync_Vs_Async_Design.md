# Sync vs. Async: When to Use Which in Design

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You order food at two restaurants. Restaurant A: The waiter takes your order, goes to the kitchen, and STANDS there watching the chef cook. Twenty minutes. He brings your food. He served only you in 20 minutes. One customer. One waiter. Blocked. Restaurant B: The waiter takes your order, puts it on a board, and immediately takes the next customer's order. The chef cooks in the background. Food arrives when ready. The waiter served 10 customers in 20 minutes. Same food. Different model. Restaurant A is synchronous. Restaurant B is asynchronous. In software design, when do you use which? Let me show you.

---

## The Story

Picture Restaurant A. You order. The waiter walks to the kitchen. Stays. Watches. The chef chops. Sautés. Plates. Twenty minutes. The waiter does nothing else. You wait. Other customers wait. One waiter. One order at a time. Inefficient. But simple. You get your food when it's done. Direct. Predictable. That's synchronous. The caller (you) waits. The worker (waiter) blocks. One-to-one. Blocking.

Picture Restaurant B. You order. The waiter writes it down. Puts it on the board. Turns. Takes the next order. And the next. The chef works through the board. Food goes out when ready. The waiter served 10 people. The chef cooked 10 meals. Same 20 minutes. Ten times the throughput. That's asynchronous. The caller (you) gets acknowledgment. "Order received." The work happens in the background. You're free. The waiter is free. Decoupled. Efficient. But more complex. When is your food ready? You might check back. Or they call your number. Different flow.

**Synchronous in software:** User sends request. Waits. Gets response. The caller blocks. Simple. Easy to reason about. But if the work takes 10 minutes, the user waits 10 minutes. The thread waits 10 minutes. The connection stays open. One slow request ties up resources.

**Asynchronous in software:** User sends request. Gets acknowledgment immediately. "We got it." Result comes later—callback, webhook, polling, or notification. Faster perceived response. But complex. How does the user know when it's done? Retries? Failure handling? More moving parts.

**When sync:** Simple CRUD. Reads. User needs immediate answer. Login. Search. "What's my balance?" **When async:** Long-running tasks. Video encoding. Email sending. Report generation. Bulk operations. Event-driven flows. When "I'll get back to you" is acceptable.

---

## Another Way to See It

Think of a phone call. Sync. You talk. They respond. You wait. Real-time. Or sending a letter. Async. You mail it. You don't wait at the mailbox. You go home. Reply arrives days later. Different use cases. Urgent? Call. Can wait? Letter.

Or a doctor's office. Sync: you sit in the room, doctor comes, you get diagnosis. Async: they take your samples, send to lab, call you with results later. Both valid. Context decides. Same in software. Context decides.

---

## Connecting to Software

**Sync in design:** REST API. Client calls. Server processes. Returns. Client waits. Simple. Predictable. Good for: get user, create order, validate token. Latency = processing time. User expects to wait.

**Async in design:** Client sends request. Server returns 202 Accepted. "We're on it." Background worker processes. When done: webhook, or client polls, or push notification. Good for: video encoding, PDF generation, email campaigns, data exports. Latency = "acknowledged" fast. Result = later.

**Hybrid—video upload example:** User uploads a 500 MB video. Sync: "Upload received." Fast. User sees confirmation. Async: encoding happens in background. Transcode to multiple resolutions. Generate thumbnails. Extract metadata. When done: "Your video is ready." Push notification. Email. User didn't wait. Server did the work. Best of both. Quick acknowledgment. Slow work in background. This is the common pattern for large operations. Acknowledge fast. Process slow. Notify when done.

---

## Let's Walk Through the Diagram

```
    SYNC                                  ASYNC

    User ──► Request ──► Server           User ──► Request ──► Server
                │                              │
                │  Process (user waits)         │  "202 Accepted"
                │                              │  User gets ack immediately
                │                              │
                ▼                              ▼
    User ◄── Response                         [Background worker]
    (10 min later)                                  │
                                                   │  Process
                                                   ▼
                                            User ◄── Webhook / Poll / Notify
                                            (10 min later, but didn't wait)
```

Sync: wait together. One request. One response. Blocking. Async: acknowledge fast, complete later. Decoupled. Non-blocking. Choose based on user expectation. Choose based on operation duration.

---

## Real-World Examples (2-3)

**Example 1: Stripe payment.** Checkout is sync. User clicks pay. Request goes to Stripe. Stripe charges. Returns success or failure. User waits 2–3 seconds. They need to know now. But refund processing? Sometimes async. Refund initiated. Webhook when completed. Different operations, different models. User expectation drives the choice.

**Example 2: Netflix.** Start watching? Sync. "Play" returns stream URL. Fast. But "Add to My List" across devices? Might trigger async sync. Profile update in background. You get confirmation. Full sync later. Hybrid. Sync for immediate feedback. Async for propagation.

**Example 3: Google Drive.** Upload file? Sync for small files. Immediate confirmation. Async for large. "Uploading..." progress bar. In background. "Upload complete" when done. Big file = async. Small = sync. Size and latency drive the choice. Rule of thumb: over a few seconds? Consider async.

---

## Let's Think Together

User uploads a 500 MB video. Sync = wait 10 minutes for processing? Or async = "Upload received, we'll notify you when ready"?

Async. Definitely. 10 minutes of blocking? User closes the tab. Connection might timeout. Server holds the connection. Wastes resources. Async: "Upload received. We're processing. We'll email you when it's ready." User leaves. Server processes. User checks back later or gets email. Better UX. Better resource use. Sync for small, fast operations. Async for large, slow ones. Rule of thumb: if it takes more than a few seconds, consider async. If the user can leave and come back, async. If they need the answer to proceed, sync.

---

## What Could Go Wrong? (Mini Disaster Story)

A team builds a "Generate Report" feature. Sync. User clicks. Server runs a 5-minute query. Builds PDF. Returns. User waits 5 minutes. Browser timeout at 2 minutes. Request fails. User clicks again. Two reports generated. Chaos. Wasted compute. Confused user. The fix: async. "Report requested. We'll email it to you in 10 minutes." User gets confirmation. Leaves. Report arrives. No timeout. No duplicate. No wasted connections. The lesson: long-running = async. Don't make users wait for what can happen in the background. Sync has a timeout. Async doesn't. Design for the duration. Design for the user.

---

## Surprising Truth / Fun Fact

Many "sync" APIs are actually async under the hood. The server receives the request, queues it, returns quickly from a worker. The client thinks it's sync—they sent one request, got one response. But internally, the server used async patterns. The boundary between sync and async can be at different layers. What the user sees (sync) vs. what the system does (async). Design for the user. Implement for scale. You can have sync semantics with async implementation. Best of both.

---

## Quick Recap (5 bullets)

- **Sync:** User waits for response. Simple. Good for fast, immediate-answer operations.
- **Async:** User gets acknowledgment, result later. Good for long-running tasks, background work.
- **When sync:** CRUD, reads, login, search, anything under a few seconds.
- **When async:** Video encoding, email, reports, bulk ops, anything that could take minutes.
- **Hybrid common:** Quick ack (sync), slow work (async), notify when done.

---

## One-Liner to Remember

**Sync: the waiter watches the chef. Async: the waiter keeps taking orders. Use sync when the user must wait. Use async when they shouldn't.**

---

## Next Video

Next: **Queue vs. direct RPC.** Walk to their desk and wait? Or leave a note and check back later? When to use which. See you there.
