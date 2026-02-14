# Event-Driven Architecture: Overview

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A town with a bell tower. Bell rings at noon—lunch time. Bell rings three times—fire! Everyone hears the bell. Everyone reacts according to their role. Firefighters rush to the fire station. Teachers evacuate schools. Parents pick up kids. Nobody told each individual what to do. The event—the bell ringing—triggered independent actions. That's event-driven architecture.

---

## The Story

Event-driven architecture means: something happens (an event). Producers publish it. Consumers react. No central orchestrator saying "you do this, you do that." Each consumer decides for itself. Loose coupling. Producer doesn't know who's listening. Add a new consumer? Just subscribe. Producer doesn't change.

An event is a fact. "Order Placed." "User Signed Up." "Payment Completed." It happened. Past tense. Immutable. Consumers use it. One consumer sends a confirmation email. Another updates analytics. Another reserves inventory. They don't call each other. They all react to the same event.

Contrast with request-response. "Order service, please reserve inventory." Order service calls inventory service. Waits. Blocked. Tight coupling. If you add "send to fulfillment," order service must call fulfillment too. More coupling. More latency. Event-driven: order service publishes "Order Placed." Inventory, fulfillment, email—all subscribe. Order service doesn't wait. Doesn't care who subscribes. Done.

---

## Another Way to See It

Think of a news alert. Earthquake in Tokyo. Reuters publishes the story. CNN, BBC, local stations—they all pick it up. They don't ask Reuters "what should I do?" They decide: break into programming, update the website, send push notifications. One event. Many independent reactions. Reuters doesn't know or care. Event-driven.

Or a doorbell. You ring it. Dog barks. Kid runs to the door. Spouse pauses the movie. The doorbell doesn't instruct them. It's an event. Each reacts. Simple.

---

## Connecting to Software

In software, events flow through a message broker or event stream. Kafka, RabbitMQ, AWS EventBridge, Redis Streams. Producer publishes to a topic or channel. Consumers subscribe. At-least-once or exactly-once delivery. Order matters? Use a partitioned topic (e.g., Kafka partition by order ID). Order doesn't matter? Fan-out to many consumers.

Event schema matters. Version your events. "OrderPlaced v1" has fields X, Y. "OrderPlaced v2" adds Z. Consumers handle both or evolve. Schema registry (Confluent, AWS Glue) helps.

---

## Let's Walk Through the Diagram

```
    REQUEST-RESPONSE (Tight Coupling)        EVENT-DRIVEN (Loose Coupling)

    Order Service ──► Inventory Service      Order Service ──► [Event: Order Placed]
           │                    │                    │
           │                    │                    ▼
           │                    │              ┌─────────────┐
           │                    │              │ Event Broker│
           │                    │              │  (Kafka, etc)│
           └──► Fulfillment ◄───┘              └──────┬──────┘
                  (Order waits for everyone)           │
                                                      ├──► Inventory (subscribe)
                                                      ├──► Email (subscribe)
                                                      ├──► Analytics (subscribe)
                                                      └──► Fulfillment (subscribe)

    Order blocks. Coupled.                        Order publishes. Done. Consumers react.
```

---

## Real-World Examples (2-3)

**Example 1: Uber.** Ride requested. Event published. Dispatch service subscribes—assigns driver. Pricing service subscribes—calculates fare. Notification service subscribes—notifies rider and driver. Analytics subscribes. Each does its job. No service calls another for this flow. Events drive it.

**Example 2: Netflix.** User plays a video. Event: "Playback Started." Recommendations service reacts—update "continue watching." Billing reacts—track usage. CDN analytics react. Loose coupling. Add a new subscriber? No change to playback service.

**Example 3: E-commerce checkout.** Order placed. Event. Inventory decrements. Payment processes. Confirmation email sends. Loyalty points update. Warehouse gets pick list. All from one event. If you add "send to CRM," you add a subscriber. No change to order service.

---

## Let's Think Together

**When is event-driven better than request-response?**

When you have multiple independent reactions. When you don't need an immediate answer. When you want to add consumers without changing producers. When order service shouldn't block on "send email." Async, loose coupling wins. When you need a direct answer—"is this item in stock?"—request-response is simpler. Sync has its place.

**What about ordering? What if email must send before fulfillment?**

Events don't guarantee order across consumers. Each consumer processes at its own pace. If you need "A then B," options: (1) one consumer does A, publishes event, another does B. (2) Saga/choreography with sequence. (3) Or accept eventual consistency. Often "email and fulfillment in parallel" is fine. Depends on domain.

---

## What Could Go Wrong? (Mini Disaster Story)

A company builds event-driven order flow. Order placed → inventory, payment, shipping. All async. One day: payment succeeds. Inventory fails (out of stock). Shipping already started. Customer charged. No product to ship. Chaos. They fixed it with Saga pattern: compensating actions. Payment succeeded but inventory failed? Refund. Rollback. Event-driven doesn't magically solve consistency. You need to design for failure. Compensation. Idempotency.

---

## Surprising Truth / Fun Fact

Event sourcing takes event-driven further. You don't just react to events—you *store* them as the source of truth. "Order Placed," "Payment Completed," "Shipped." Replay them to get current state. Full audit trail. Time travel. Event-driven is about communication. Event sourcing is about storage. Related but different.

**Scaling consumers:** Add more consumer instances. Kafka consumer groups. Each partition consumed by one consumer in the group. Scale horizontally. More consumers, more throughput. Events are the contract. Consumers are stateless (or state in their own DB). Scale independently. Event-driven naturally supports this.

**Dead letter queues:** Consumer fails to process an event. Retry a few times. Still fails? Move to dead letter queue (DLQ). Don't block the main queue. Investigate later. Replay when fixed. DLQs are essential. Without them, one bad event can stall the whole pipeline. Design for failure. Always have a DLQ.

**Ordering:** For partitioned topics (e.g., Kafka), order is preserved within a partition. Partition by order ID: all events for order 123 go to the same partition. Ordering guaranteed for that order. Across partitions, no order. Choose partition key wisely. Balance parallelism (many partitions) with ordering needs. Consumer groups let you scale: multiple consumers, each handles a subset of partitions. Throughput scales. Order within partition preserved. Start simple. Add complexity when you need it. Event-driven is powerful but has a learning curve. Master the basics first.

---

## Quick Recap (5 bullets)

- **Event-driven** = something happens (event), producers publish, consumers react independently. No central orchestrator.
- Events are facts: "Order Placed," "User Signed Up." Immutable. Past tense.
- Loose coupling: producer doesn't know consumers. Add subscribers without changing producers.
- Use a message broker or event stream: Kafka, RabbitMQ, EventBridge. Publish-subscribe.
- Design for failure: idempotency, compensating actions, ordering when it matters.

---

## One-Liner to Remember

Event-driven: when the bell rings, everyone reacts. No one told them what to do. The event did.

---

## Next Video

Next up: **Serverless**—taxi vs owning a car. Pay only when your code runs. No servers to manage. But cold starts and limits.
