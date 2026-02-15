# Notification System: Queue and Scaling

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Breaking news. 10 million users need to be notified within 5 minutes. You can't call 10 million phone numbers one by one. You need PARALLELISM. Queue the notifications. 100 workers pick from the queue. Each sends thousands per minute. Fan-out. Scaling notifications is about queues, workers, and rate limits from providers. Let's design it together.

---

## The Story

One worker. One thread. Sends 1 notification per second. 10 million notifications = 10 million seconds = 115 days. Impossible. 100 workers. Each does 10 per second. 10 million / 1000 per second = 10,000 seconds = 2.7 hours. Better. 1000 workers. 10 per second each. 10 million / 10,000 per second = 1000 seconds = 16 minutes. Good. But wait—providers have rate limits. Twilio: 100 SMS per second per account. FCM: 500K push per second. You're bounded by the slowest channel. Design for the bottleneck. Queue absorbs the burst. Workers drain at provider speed. Don't overload. Respect limits.

---

## Another Way to See It

Think of a theme park. 10,000 people want to ride. One ride. 10 people per minute. Line would be 1000 minutes. Add 10 rides. 100 people per minute. 100 minutes. Add 100 rides. 1000 per minute. 10 minutes. Queues are the line. Workers are the rides. Parallelism is the solution. But: rides have safety limits. Don't exceed. Providers have rate limits. Same idea.

---

## Connecting to Software

**Architecture.** Event triggers 10M notifications. Notification service fans out: 10M messages to queue. One queue per channel (SMS queue, push queue, email queue). Each channel scales independently. SMS workers: 50 workers. Each pulls 2 messages per second. 100 SMS/sec. At Twilio limit. Push workers: 500 workers. Each pulls 1000 per second. 500K/sec. At FCM capacity. Email workers: 200 workers. SES allows higher. Scale as needed. Queues: SQS, RabbitMQ, Kafka. Durable. Retry on failure. Don't lose a notification.

**Provider rate limits.** Twilio: ~100 SMS/sec (varies by number). Exceed? 429. Back off. FCM: 500K push/sec. Rarely the limit. SES: 14 emails/sec per account (can request increase). Plan workers to stay under. Use multiple provider accounts. Shard by user_id. Account 1 handles users A-M. Account 2 handles N-Z. Double the limit. Architecture supports it.

**Deduplication.** User gets "order shipped" twice. Bug. Or retry. Prevent: notification_id + user_id. Before send, check: already sent? Skip. Idempotent. Important for retries. Inbox pattern: store notification in user's inbox. Mark read/sent. Dedup at read time. Both work.

**Retries.** Send fails. Provider timeout. Network error. Retry. Exponential backoff. 3-5 attempts. Dead letter queue for permanent failures. Don't block the queue. Move to DLQ. Alert. Investigate. User might need manual resolution.

---

## Let's Walk Through the Diagram

```
NOTIFICATION - QUEUE SCALING
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   EVENT: Breaking news → 10M users need push                     │
│         │                                                        │
│         ▼                                                        │
│   Fan-out: 10M messages to PUSH QUEUE                            │
│         │                                                        │
│         │  Workers (500) each pull 2000/min                    │
│         ▼                                                        │
│   500 × 2000 = 1M/min = 16,666/sec                               │
│   FCM limit: 500K/sec → need 34 seconds at peak                  │
│   With 500 workers: 10M / 500 = 20K per worker                   │
│   20K at 33/sec = 10 min (FCM allows)                            │
│                                                                  │
│   QUEUE PER CHANNEL:                                             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐                         │
│   │ SMS Q   │  │ Push Q  │  │ Email Q │                         │
│   └────┬────┘  └────┬────┘  └────┬────┘                         │
│        │            │            │                               │
│   Workers: 50   Workers: 500  Workers: 200                      │
│   Limit: 100/s  Limit: 500K/s  Limit: 14/acc (scale accounts)   │
│                                                                  │
│   Retry → DLQ. Dedup: notification_id. Rate limit: backoff.      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Event fans to queue. Workers pull. Each channel has its own queue and worker pool. Size workers to provider limits. Don't exceed. Retry failures. Dedupe. 10M in 5 min? Push can do it. SMS? 100/sec = 100 per sec. 10M / 100 = 100K seconds = 27 hours. SMS can't do 10M in 5 min with one account. Need 200+ Twilio numbers. Or batch. Design knows the math.

---

## Real-World Examples (2-3)

**Twitter.** Tweet from celebrity. Millions of followers. Push to all. Queue. Workers. FCM. Delivered in minutes. Same pattern. Scale workers to need.

**Netflix.** New season drops. Email 100M users. Batch. Spread over hours. Don't need 5 minutes. Email is async. Queue for days. Workers drain. No rush. Different SLA than breaking news.

**Uber.** Trip assigned. Push to driver. One notification. Low volume. But latency matters. Sub-second. Queue still. But worker pool tuned for latency. Not throughput. Same components. Different tuning.

---

## Let's Think Together

**"10M users need push in 5 min. FCM handles 500K/sec. Can we send all in time? What about retries for failed ones?"**

500K/sec × 300 sec = 150M. 10M is under. Yes, we can. Time: 10M / 500K = 20 seconds. Theoretical. With 500 workers, each sending 1000/sec: we're at limit. 20 seconds. Done. Retries: 1% fail. 100K retries. Add to queue. Resend. Another 0.2 seconds. Total: ~25 seconds. Well under 5 min. Buffer for startup, network, etc. Design: size workers for 500K/sec total. Retry queue. Don't block main queue. Retries can be slower. Users already got it or will get it soon. Failed retries → DLQ. Manual or delayed retry. Don't lose them.

---

## What Could Go Wrong? (Mini Disaster Story)

A company sends a marketing push. 5 million users. One worker. "We'll scale later." Worker pulls 10 per second. 5M / 10 = 500K seconds = 5.7 days. Campaign is over. Nobody got the push in time. Post-mortem: "We needed 500 workers." They add workers. Next campaign: 500 workers. But they hit FCM limit. 429 errors. Workers retry. Retry storm. FCM throttles more. Cascading failure. Lesson: know your limits. Size workers under limit. Test at scale. Rate limits are real.

---

## Surprising Truth / Fun Fact

During the 2020 US election, notification systems sent billions of messages. Twitter, Facebook, news apps. All at once. Queues held. Workers scaled. Providers held. The architecture—queue, workers, rate limits—is battle-tested. Design for the spike. It will come.

---

## Quick Recap (5 bullets)

- **Queue + workers:** Fan-out to queue. Workers drain. Parallelism = throughput.
- **Per channel:** Separate queue per channel. Scale independently.
- **Provider limits:** Twilio 100/sec, FCM 500K/sec. Size workers under. Multiple accounts if needed.
- **Deduplication:** notification_id. Retries don't duplicate.
- **Retries:** Exponential backoff. DLQ for permanent failures.

---

## One-Liner to Remember

**Scale notifications: queue the burst, worker the drain, respect provider limits.**

---

## Next Video

Next: authentication systems. Tokens. Flows. Login to validation. The secure building.
