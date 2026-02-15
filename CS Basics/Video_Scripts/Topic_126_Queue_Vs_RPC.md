# Queue vs. Direct RPC: When to Use Which?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two ways to ask a colleague for help. Way 1: Walk to their desk. Tap their shoulder. Ask directly. WAIT for the answer. Fast if they're free. Terrible if they're busy—you stand there awkwardly. Blocked. Way 2: Leave a note on their desk. "Please review this by EOD." You go back to your work. They handle it when free. You check back later. Decoupled. No waiting. In software, Way 1 is RPC. Way 2 is a queue. When do you use which? Let me show you.

---

## The Story

Picture Way 1. You need an answer. You walk over. "Hey, can you review this?" They're on a call. You wait. Five minutes. Ten minutes. You're blocked. You could be doing other work. But you need their answer to proceed. So you wait. That's RPC. Remote Procedure Call. Synchronous. Direct. You send. You wait. You get. Real-time. But blocking. If they're slow or unavailable, you're stuck.

Picture Way 2. You leave a note. "Review by EOD." You return to your desk. They'll get to it. You'll check back. Or they'll ping you. Decoupled. You're not blocked. They process when ready. The note sits in a queue. First in, first out. Or prioritized. They work through it. That's a queue. Asynchronous. Buffered. Non-blocking. But you don't get immediate answer. Eventual. You need to handle "when will it be done?"

**RPC (Remote Procedure Call):** Synchronous. Direct. Real-time response. Like a function call across the network. You send a request. You wait. You get a response. gRPC, REST, Thrift. Fast. Simple. But the caller blocks. If the callee is slow or down, the caller waits or fails. Tight coupling. Caller and callee must be up at the same time.

**Queue:** Asynchronous. Decoupled. Buffered. Producer sends a message. Puts it in a queue. Returns. Consumer processes when ready. RabbitMQ, SQS, Kafka. No blocking. Handle traffic spikes—queue absorbs. But no immediate response. Eventual. You don't know exactly when it'll be done. Trade-offs. Always.

---

## Another Way to See It

Think of a drive-through. RPC. You order. You wait at the window. You get food. Direct. Synchronous. You're blocked until they hand you the bag. Or a food delivery app. You order. Kitchen gets the order (queue). They cook. Driver picks up. You get it later. Decoupled. Asynchronous. Both deliver food. Different flow. Different expectations. Different latency. Or a bank: ATM withdrawal? RPC. You need the money now. Bank statement? Queue. Generated overnight. You get it tomorrow. Context decides. Need now? RPC. Can wait? Queue.

---

## Connecting to Software

**RPC use cases:** "Charge this card." Need yes/no now. "Is this user authenticated?" Need answer now. "Get user profile." Need data now. "Validate coupon." Need result before checkout. Anything where the next step depends on the immediate response. User is waiting. Blocking is acceptable. Result is required to proceed.

**Queue use cases:** "Send welcome email." Can wait. "Update analytics." Can wait. "Process order fulfillment." Can wait. "Sync to data warehouse." Can wait. "Notify other services." Decouple. If the consumer is slow, messages pile up. No timeouts. No blocking. Queue absorbs. Spikes? Queue absorbs. Consumer down? Queue holds. Retry when up. Resilience.

**Comparison table:**

| | RPC | Queue |
|---|---|---|
| Latency | Immediate | Eventual |
| Coupling | Tight (caller waits) | Loose (decoupled) |
| Blocking | Yes | No |
| Spike handling | Poor (caller blocks) | Good (queue absorbs) |
| Failure | Caller fails with callee | Queue holds, retry later |
| Use when | Need result now | Can wait |

---

## Let's Walk Through the Diagram

```
    RPC (Direct)                         QUEUE (Decoupled)

    Service A ──────► Service B           Service A ──► [Queue] ──► Service B
          │                                    │            │
          │  Request                           │  Publish   │  Consume
          │  Wait...                            │  Return    │  Process
          │                                     │  immediately  when ready
          ▼                                    │            │
    Service A ◄────── Service B                 │  No wait   │  Async
          │                                    │            │
    Response. Blocking.                        Decoupled. Buffered.
```

RPC: call and wait. Direct. Synchronous. Queue: send and forget (consumer handles). Indirect. Asynchronous. Choose based on latency requirement. Choose based on coupling tolerance.

---

## Real-World Examples (2-3)

**Example 1: Stripe.** Payment API is RPC. You call charge. You get success or decline. Now. Can't queue that—user is waiting at checkout. But webhook delivery? Queue. Stripe sends to your endpoint. If your endpoint is down, Stripe retries. Queue behavior. Different operations. Different patterns.

**Example 2: Uber.** Match rider to driver? Needs to feel real-time. RPC or WebSocket. "Where's my driver?" RPC. But "Send receipt email"? Queue. "Update analytics"? Queue. Mix of both. Payment? RPC. Receipt? Queue. Same app. Different needs.

**Example 3: Netflix.** "Play video"? RPC—get stream URL. "Add to continue watching"? Could be queue—eventual consistency okay. "Recommendation update"? Queue. Batch processing. Different latency requirements. Design each operation. Choose the right pattern.

---

## Let's Think Together

Payment processing: Should the checkout page wait for the payment result (RPC) or get "Processing..." and be notified later (queue)?

Usually RPC. User is at checkout. They need to know: paid or not. Wait for payment gateway. Get success or failure. Show confirmation or error. Queue would mean: "We're processing. Check your email in 5 minutes." Bad UX for checkout. User would leave. Abandon cart. Lost sale. BUT. Some flows use queue. High-risk orders. Manual review. "We're reviewing. We'll notify you." That's queue. Bank transfer? Queue. "Payment initiated. Will clear in 2-3 days." So: instant payment (card charged now) = RPC. Delayed (manual review, bank transfer) = queue. Context matters. User expectation matters. Design for the flow. Design for the expectation.

---

## What Could Go Wrong? (Mini Disaster Story)

A team builds order processing. They use RPC everywhere. Order service calls inventory. Calls payment. Calls shipping. All synchronous. One day payment service is slow. 10-second latency. Order service waits. Connections pile up. Thread pool exhausted. Order service goes down. Cascade. Inventory calls fail. Shipping calls fail. Everything fails. They should have queued. Order created → queue → payment worker. Order service returns fast. "Order received." Payment happens in background. Payment slow? Queue absorbs. Workers retry. No cascade. Order service stays up. The lesson: when the callee can be slow or unreliable, consider a queue. RPC assumes the other side is fast and up. Queue assumes nothing. Design for failure. Queue when you can't assume.

---

## Surprising Truth / Fun Fact

Kafka—often thought of as a queue—is used for both streaming and messaging. Companies use it for "event sourcing" and "log streaming" where the consumer reads at their own pace. It's like a queue with persistence and replay. You can "re-read" from the beginning. RPC can't do that. Once the response is sent, it's gone. Queue/Kafka: the message stays. New consumers can join and catch up. Different guarantee. Choose based on what you need. Replay? Kafka. Fire-and-forget? SQS. Need response now? RPC.

---

## Quick Recap (5 bullets)

- **RPC:** Synchronous, direct, immediate response. Good for: auth, payment confirmation, real-time needs.
- **Queue:** Asynchronous, decoupled, buffered. Good for: email, analytics, decoupling, spike handling.
- **RPC blocks.** If callee is slow or down, caller suffers. **Queue absorbs.** Consumer processes when ready.
- **Checkout payment:** usually RPC (user waits). **Welcome email:** queue (can wait).
- **Choose based on:** Do you need the result now? RPC. Can it be eventual? Queue.

---

## One-Liner to Remember

**RPC: walk to their desk and wait. Queue: leave a note, they'll get to it. Need answer now? RPC. Can wait? Queue.**

---

## Next Video

Next: **Backpressure.** The water pipe that could burst. Or the valve that says "slow down." How to design for overload. See you there.
