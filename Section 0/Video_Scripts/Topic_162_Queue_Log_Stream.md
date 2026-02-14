# When to Use a Queue vs a Log vs a Stream

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Three tools in a carpenter's workshop. Hammer: hit the nail. Job done. Move on. Notebook: record every measurement. Refer back anytime. Conveyor belt: work flows continuously. Multiple workers process items as they pass. Different tools. Different purposes. Use the wrong one—and you waste time. Queue. Log. Stream. When do you pick which?

---

## The Story

Imagine a carpenter's workshop. **Hammer:** You hit the nail. Job done. Move to next. One task. One action. **Notebook:** You record every measurement. Wood length. Cut angle. Refer back anytime. Permanent record. **Conveyor belt:** Work flows continuously. Boards move. One worker measures. Next cuts. Next sands. Real-time. Multiple workers. Different stages. Three tools. Three patterns. In software: queue = hammer. Task distribution. Log = notebook. Event history. Stream = conveyor. Real-time processing. Windowed aggregations. Use the right one.

---

## Another Way to See It

Think of a post office. **Queue:** Letters in a bin. Workers take one. Process. Mail it. Next. Task queue. **Log:** Every letter scanned. Stored. Customer can ask "where's my letter?" Track history. Audit. **Stream:** Letters on a conveyor. Automated sorting. "All letters to Delhi this hour—count them." Real-time aggregation. Different needs. Different systems.

---

## Connecting to Software

**Queue:** Task distribution. Work queue. Request/reply. One consumer per message. "Process this. Done. Next." RabbitMQ. SQS. Use when: you have discrete tasks. Workers. Throughput. No need to replay. No need for multiple consumers of same message. Simple. Fast. Job done.

**Log:** Event sourcing. Audit trail. Replay. Multiple consumers reading same events. Append-only. Keep history. Kafka. Kinesis. Use when: events are the source of truth. Many downstream systems. Replay. "What happened?" Log answers.

**Stream:** Real-time processing. Continuous data flow. Windowed aggregations. "Count events per minute." "Running total." "Join two streams." Kafka Streams. Flink. Spark Streaming. Use when: you need to process data as it arrives. Aggregate. Transform. Window. Not just "consume and done." Continuous computation.

**Decision framework:** Need one consumer per message? Queue. Need multiple consumers, replay, audit? Log. Need real-time aggregation, windows, joins? Stream.

---

## Let's Walk Through the Diagram

```
    QUEUE vs LOG vs STREAM

    QUEUE:                    LOG:                     STREAM:
    Task → Worker → Done       Event → Storage          Event → Process
    [A][B][C]                  [A][B][C][D]...          [A][B][C]---
      ↓                          ↓   ↓   ↓                ↓  ↓  ↓
    Worker takes A              Many readers         Window: count last 5min
    A gone                      Replay possible       Aggregation. Continuous.
```

Queue: distribute. Log: persist and replay. Stream: compute over time. Different abstractions. Different tools.

---

## Real-World Examples (2-3)

**Example 1: Image resize.** Queue. 1000 images. 10 workers. Each takes one. Resize. Upload. Done. Task distribution. Queue. Simple. You don't need to replay. You don't need multiple consumers of the same image. One worker. One task. Queue fits. RabbitMQ. SQS. Perfect.

**Example 2: Order events.** Log. OrderCreated. PaymentDone. Shipped. Multiple services: inventory, analytics, notifications. All need the same events. Inventory: update stock. Analytics: update dashboards. Notifications: send emails. With a queue, you'd produce to three queues. Or have one consumer fan out. Fragile. With a log: all three subscribe. Same topic. Same events. Replay for new service? Yes. Add analytics v2 next month? Subscribe. Read from beginning. Queue can't do that. Log can. Kafka. Right choice.

**Example 3: Real-time dashboard.** Stream. "Orders per minute." "Revenue last hour." Events flow. Stream processor. Window. Aggregate. Emit. Kafka Streams or Flink. Stream. Real-time. Windows. Aggregation.

---

## Let's Think Together

**Real-time fraud detection on payment events. Queue, log, or stream?**

Stream. You need to process payments as they arrive. Aggregate. "Same card, 5 transactions in 2 minutes?" Window. Pattern. Alert. Queue: one consumer. No window. No aggregation across messages. Log: you have history. But you need real-time processing. Stream: read from log (Kafka). Process. Window. Aggregate. Detect. Stream fits. Kafka Streams. Flink. Or Kinesis Data Analytics.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used a queue for "click events." Millions per minute. They wanted "clicks per user per hour." Queue: each click processed once. Gone. No way to aggregate across clicks. They had to store everything in a DB. Query. Slow. Expensive. Should have used a stream. Kafka. Window. Aggregate. Emit. Real-time. Lesson: aggregation over time? Stream. Queue is for tasks. Not analytics.

---

## Surprising Truth / Fun Fact

Kafka is both a log and a stream platform. Kafka (broker) = log. Kafka Streams = stream processing on top of that log. Same data. Two views. Read as log. Or process as stream. One infrastructure. Flexible. AWS has similar: Kinesis (log) + Kinesis Data Analytics (stream). The line between log and stream is often the same product. Different APIs. You don't have to choose "queue or log or stream" as separate products. Often: one log. Many consumers. Some do task distribution (queue-like). Some do aggregation (stream-like). The log is the foundation. Build on it. Choose the abstraction that fits your use case. The underlying storage might be the same.

---

## Quick Recap (5 bullets)

- **Queue:** One consumer per message. Task distribution. RabbitMQ, SQS. Discrete jobs.
- **Log:** Persist. Multiple consumers. Replay. Kafka, Kinesis. Events. Audit.
- **Stream:** Real-time processing. Windows. Aggregations. Kafka Streams, Flink. Analytics.
- **Choose:** Tasks? Queue. Events, replay, many consumers? Log. Real-time aggregation? Stream.
- **Often:** Log + Stream together. Kafka stores. Kafka Streams processes. Same data. The log is the source. The stream is the computation. One infrastructure. Two views. When you're choosing, ask: do I need to distribute work? Queue. Do I need to persist and replay? Log. Do I need to aggregate over time? Stream. Sometimes you need two. Event stream in Kafka. Stream processor for real-time. Batch job for historical. All from same log. Architecture follows the questions you ask.

---

## One-Liner to Remember

**Queue: do the task. Log: keep the history. Stream: compute over time. Match the tool to the job.**

---

## Next Video

We've talked about events. Logs. Streams. But where do those events come from? Often: your database. Every change. How do we capture that? CDC—Change Data Capture. The spy camera on your database. That's next. See you there.
