# SAGA: Choreography vs Orchestration

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A dance performance. Two ways to run it. Choreography: every dancer knows their moves. They watch each other. React. No one on stage telling them what to do. Orchestration: a conductor stands there. Points. "You. Now. You. Now." Central control. Both get the dance done. But the experience? Completely different. That's how we coordinate SAGAs too.

---

## The Story

Imagine a dance performance. **Choreography:** Each dancer knows their part. They've practiced. They react to each other. Dancer A finishes a move—Dancer B starts. No director on stage. Self-organized. Events flow. One action triggers the next. **Orchestration:** A conductor stands on stage. Points to each dancer. "You start. Now you. Now you." Central control. One brain. Everyone follows. Two ways to coordinate. Same outcome. Different structure.

In SAGAs, we have the same choice. Choreography: each service listens for events. Reacts. Publishes. No central controller. Orchestration: a SAGA orchestrator tells each service what to do. Step by step. One coordinator. Two designs. Different trade-offs.

---

## Another Way to See It

Think of a kitchen. **Choreography:** Each cook knows the recipe. When the appetizer is plated, the main course cook starts. When main is done, dessert cook starts. No head chef calling orders. Just flow. **Orchestration:** Head chef stands in the middle. "You—appetizer. You—main. You—dessert." Explicit commands. Clear chain of control. Both kitchens can produce a meal. The orchestrated one is easier to understand. The choreographed one is more flexible—but harder to debug when something breaks.

---

## Connecting to Software

**Choreography:** Each service subscribes to events. Order service creates order → publishes "OrderCreated." Payment service listens → charges card → publishes "PaymentCompleted." Inventory service listens → reserves stock → publishes "InventoryReserved." No central coordinator. Services are decoupled. They only know the event schema. Loose coupling. Resilient. Add a new step? New service subscribes. No changes to existing ones. But: Who started the SAGA? Who handles compensation when step 4 fails? Flow is implicit. Distributed. Hard to trace. Hard to debug. "Why didn't my order complete?" Good luck. You need correlation IDs. Distributed tracing. And even then, choreography can be a maze. Choose when you value decoupling over visibility.

**Orchestration:** A SAGA orchestrator (orchestration service) holds the workflow. "Step 1: call inventory service—reserve. Step 2: call payment service—charge. Step 3: call shipping service—ship." The orchestrator makes the calls. Knows the order. Knows what to compensate if something fails. Centralized logic. Clear flow. Easier to understand. But: The orchestrator is a single point of coordination. If it's down, no SAGAs run. And it can become a bottleneck.

**Trade-offs:** Choreography = loosely coupled, resilient, but complex to trace. Orchestration = clear flow, easier debugging, but orchestrator dependency.

---

## Let's Walk Through the Diagram

```
    CHOREOGRAPHY                          ORCHESTRATION

    [Order] --OrderCreated--> [Payment]       [Orchestrator]
       |                           |                |
       |                           |                |--reserve---> [Inventory]
       |                           |                |<--ok---------|
       |                           |                |--charge-----> [Payment]
       |    --PaymentDone--------->|                |<--ok---------|
       |                           |                |--ship-------> [Shipping]
    [Inventory] <--ReserveStock--  |                |<--ok---------|
       |                           |                |
    Events flow. No central       One coordinator. Sequential
    controller.                   calls. Clear flow.
```

Choreography: events drive flow. Orchestration: orchestrator drives flow. Choose based on team structure and debug needs.

---

## Real-World Examples (2-3)

**Example 1: Uber EATS (choreography-style).** Order placed → kitchen notified. Kitchen confirms → driver assigned. Driver picks up → customer notified. Events flow. Many services. No single orchestrator. Resilient. But when "order stuck" happens, tracing is hard. Which service dropped the ball?

**Example 2: Banking transfer (orchestration).** Transfer service orchestrates: debit Account A, credit Account B, send notification. One service. Clear flow. Easy to add compensations. Easy to log. Debugging: check orchestrator logs. Done.

**Example 3: Netflix (hybrid).** Some flows choreographed. Some orchestrated. Event-driven for real-time updates. Orchestrated for complex, multi-step workflows. Use both. Context matters.

---

## Let's Think Together

**10-step SAGA with choreography. Something fails at step 7. How do you trace what happened?**

Tricky. Step 7 published an error event. Maybe. Or maybe it never published. Or published to the wrong topic. You need: (1) Correlation IDs—one ID flows through all events. (2) Event logs—every service logs what it published and consumed. (3) Possibly a workflow engine that reconstructs the flow from events. Choreography is flexible. Observability is the cost. Invest in tracing. Or use orchestration for complex flows.

---

## What Could Go Wrong? (Mini Disaster Story)

A team chose choreography for a 6-step payment SAGA. "Decoupled! Scalable!" Step 4 failed. Compensation? Each service was supposed to listen for "SAGAFailed" and compensate. But service 2 had a bug. It didn't subscribe correctly. Service 1 and 3 compensated. Service 2 didn't. Inconsistent state. Money reserved, never released. Took a week to trace. Lesson: In choreography, every participant must be correct. One bug. Whole SAGA breaks. Orchestration: one place to fix.

---

## Surprising Truth / Fun Fact

AWS Step Functions is an orchestrator. You define a state machine. Each step is a Lambda or service call. Built-in retry. Built-in compensation (catch blocks). Many companies use it for SAGA orchestration. Temporal. Camunda. Same idea. Choreography vs orchestration isn't theoretical—it's a product decision. Pick the tool that fits your team. Need visibility? Orchestration. Need decoupling? Choreography. Hybrid is fine too. Some flows orchestrated. Some choreographed. Context matters. One size doesn't fit all.

---

## Quick Recap (5 bullets)

- **Choreography:** Services react to events. No central controller. Loose coupling.
- **Orchestration:** Orchestrator calls services in order. Central control. Clear flow.
- **Choreography** = harder to trace, more moving parts. **Orchestration** = easier to debug, single dependency.
- **Choose:** Simple flows, team prefers events → choreography. Complex flows, need clarity → orchestration.
- **Tools:** Step Functions, Temporal, Camunda for orchestration. Kafka, RabbitMQ for choreography.

---

## One-Liner to Remember

**Choreography: everyone reacts. Orchestration: one boss directs. Same SAGA. Different coordination. Choose based on complexity and who needs to debug.**

---

## Next Video

But how do you actually "undo" a step? Compensation isn't database rollback. You can't un-send an email. So what do you do? Compensation in SAGA—rolling back without 2PC. That's next. See you there.
