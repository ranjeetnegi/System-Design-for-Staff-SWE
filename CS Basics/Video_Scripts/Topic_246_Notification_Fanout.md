# Notification Fan-out: Scale and Dedup

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A school principal. "School closed tomorrow." 10,000 parents. Each has 2 or 3 devices. That's 25,000 notifications. Some get SMS plus push plus email. Retries create duplicates. Fan-out: one event, many recipients. At scale, one viral event means millions of notifications. And you must ensure nobody gets the same notification twice. Let's see how.

---

## The Story

One event. Many recipients. A tweet from a celebrity. Millions of followers. Each gets a push notification. One "new tweet" event. Millions of deliveries. Fan-out. The challenge: speed and resources. Deliver fast. Don't overwhelm your infrastructure. And: deduplication. User has 3 devices. Same notification to all 3. OK. But retry logic: "Did that push succeed?" If unsure, retry. User might get duplicate. "You have a new message." "You have a new message." Annoying. Or worse: charged twice for a duplicate SMS. Dedup: before sending, check "did I already send notification N to user U?" Yes? Skip. No? Send. Record. The check must be fast. Millions of checks. Distributed. That's the engineering challenge. Fan-out is simple in concept. Scale and dedup are the hard parts.

---

## Another Way to See It

Think of a radio broadcast. One signal. Millions of receivers. The broadcaster sends once. Everyone with a radio gets it. Fan-out. But what if the signal is weak? Some radios retune. Ask for repeat. The broadcaster sends again. Some listeners get it twice. Duplicate. Dedup in notifications: "Have I already delivered this to this recipient?" Yes = don't repeat. No = deliver and mark. The broadcast model scales. One-to-many. The dedup model prevents spam. Both matter. Scale the broadcast. Deduplicate the receipts.

---

## Connecting to Software

**Fan-out flow.** Event arrives. "New tweet from @celebrity." System expands: get all followers. 10 million. For each follower: create a delivery task. "Send push to user X." Queue. Workers consume. Send push. One event → 10 million queue entries. The queue is the buffer. Absorbs the burst. Workers run at 10K deliveries per second? 10 million / 10K = 1,000 seconds. 16 minutes. For one tweet. Scale workers. 100K per second. 100 seconds. Better. Or: fan-out on write vs on read. On write: pre-compute. When user follows, add to their "pending notifications" list. When tweet arrives, write to each follower's list. One write per follower. Expensive at follow time. Cheap at notify time. Tradeoff. Twitter does hybrid. Most users: on read (lazy). Celebrity with millions: on write (fan-out). Optimize per user segment.

**Dedup.** Notification ID. Per (event, recipient). Before sending: check store. "notification_123_user_456 already sent?" Redis. Or DB. Get. If exists: skip. If not: send. Set "notification_123_user_456 = sent". Idempotency key. Exactly-once delivery. The check is in the hot path. Millions per second. Redis handles it. Or: partition by user. Each user's dedup store is separate. Scale horizontally. Key design: notification_id must be deterministic. Hash(event_id, recipient_id). Same event, same recipient = same key. Always. Retries use same key. Dedup works.

**Priority.** Payment alert: high. Social notification: medium. Marketing: low. Separate queues. High-priority workers run first. Low-priority can wait. When system is overloaded, shed low priority. Keep high. Payment confirmed? Must deliver. "50% off sale"? Can wait. Or drop. Priority queues. Multiple workers. Configure correctly. Users expect it. "Why did my password reset arrive before my payment confirmation?" Priority. Get it right.

---

## Let's Walk Through the Diagram

```
NOTIFICATION FAN-OUT
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   EVENT: "New tweet from @celebrity"                             │
│        │                                                         │
│        ▼                                                         │
│   EXPAND: Get 10M followers                                      │
│        │                                                         │
│        ▼                                                         │
│   QUEUE: 10M delivery tasks (user, channel, notification_id)     │
│        │                                                         │
│        ├──► Worker 1 ──► DEDUP CHECK ──► Send? Yes ──► Push       │
│        ├──► Worker 2 ──► DEDUP CHECK ──► Send? No  ──► Skip      │
│        ├──► Worker 3 ──► ...                                    │
│        └──► Worker N                                             │
│                                                                  │
│   DEDUP: Redis key = notification_id + user_id. Set on send.    │
│   PRIORITY: High (payment) / Medium (social) / Low (marketing)   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Event arrives. System expands to 10 million recipients. Each gets a queue entry. Workers pull. Before sending, dedup check. Already sent? Skip. Not sent? Send. Record. Priority determines which queue workers drain first. High first. Low when capacity allows. The diagram shows the flow. Simple. At scale: queue depth, worker count, dedup store load. All must scale. Plan for viral. Hope for steady. Design for both.

---

## Real-World Examples (2-3)

**Twitter.** Billion users. Celebrity tweets. Millions of notifications. Fan-out at scale. They've written about it. Lazy fan-out for most. Eager for celebrities. Dedup. Exactly-once. Proven. The scale is real.

**WhatsApp.** Message notifications. Billions of users. Each message to a group: fan-out to all members. Dedup per device. Multi-device sync. Complex. They do it. Status updates. Delivery receipts. Fan-out everywhere.

**Slack.** @channel in a big workspace. One message. Thousands of users. Push notifications. Email digests. Fan-out. Dedup. "Already notified about this?" Don't repeat. They handle it. Enterprise scale.

---

## Let's Think Together

**"Breaking news alert to 50 million users. 3 channels each—push, SMS, email. 150 million deliveries. Workers: 10K deliveries per second. How long?"**

150 million / 10,000 = 15,000 seconds. 250 minutes. Over 4 hours. Too slow. Ramp workers. 100K per second. 1,500 seconds. 25 minutes. Better. Or 1M per second. 150 seconds. 2.5 minutes. Achievable with enough workers. Cost: workers cost money. 1M/sec = 100 workers at 10K each? Rough math. Scale horizontally. Or: not all channels equally urgent. Push first. SMS for high priority. Email can be batched. Hourly digest. Reduce burst. Or: tier by user. Premium users get instant. Others get batched. Business decision. The math tells you the bounds. 150M deliveries. 10K/sec. 4 hours. Decide: is that OK? If not, scale workers. Or reduce scope. Design informs the answer.

---

## What Could Go Wrong? (Mini Disaster Story)

A notification system. No dedup. User has 2 devices. Push fails on device 1. Retry. Succeeds. Push to device 2. Succeeds. Both devices get it. Good. But: push to device 1 eventually succeeds on retry. Device 1 gets it twice. User: "Why did I get the same notification twice?" Support ticket. Multiply by millions. Duplicate notifications. Annoying. For payment confirmations? User thinks they were charged twice. Panic. Support overload. Fix: dedup. notification_id + user_id + device_id. Before send: check. Sent? Skip. Simple. Implemented. Problem gone. The cost of skipping dedup: user trust. Support cost. Refunds for "double charge" that wasn't. Dedup is not optional. It's foundational. Design it in from day one.

---

## Surprising Truth / Fun Fact

Twitter's early architecture had a fan-out problem. When celebrities like Lady Gaga got millions of followers, a single tweet meant millions of database writes. Timeline generation: "get all tweets from people I follow." For Lady Gaga's followers, that was millions of timeline writes. They switched to "fan-out on write" for high-follower users. Pre-compute. Store timeline entries when the tweet is published. Expensive at write. Cheap at read. The opposite of normal users. One size doesn't fit all. Segment. Optimize per use case. That's how you scale.

---

## Quick Recap (5 bullets)

- **Fan-out:** One event → many recipients. Expand, queue, deliver. Scale workers for speed.
- **Dedup:** notification_id + user_id. Check before send. Skip if already sent. Exactly-once.
- **Priority:** Payment > social > marketing. Separate queues. Shed low when overloaded.
- **Scale:** 150M deliveries at 10K/sec = 4 hours. Ramp workers or reduce scope.
- **Fan-out on write vs read:** Pre-compute for celebrities. Lazy for normal users. Segment.

---

## One-Liner to Remember

**Fan-out is one event becoming millions of deliveries—and dedup ensures each of those millions arrives exactly once.**

---

## Next Video

Next: auth, mTLS, and the hard problem of certificate revocation.
