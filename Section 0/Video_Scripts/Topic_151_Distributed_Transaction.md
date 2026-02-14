# Distributed Transaction: Why It's Hard

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

The venue says yes. The caterer says yes. You're almost there. Then the photographer texts: "Sorry, I'm busy that day." Your wedding plan just collapsed. And now? You have to call the venue back. Cancel the caterer. Undo everything. All-or-nothing across three separate businesses—and you're the one holding the pieces together. That's not just wedding stress. That's exactly what distributed transactions feel like in software.

---

## The Story

Imagine you're planning a wedding. You book the venue. You book the caterer. You book the photographer. All three must confirm, or the wedding can't happen. The venue says yes. The caterer says yes. The photographer says: "I'm busy that day." Now you're stuck. You need to cancel the venue. Cancel the caterer. Undo everything you did. All-or-nothing—across three separate businesses. Nobody shares a ledger. Nobody coordinates for you.

In a single database, this is easy. BEGIN TRANSACTION. Do all the work. COMMIT. Or ROLLBACK. One system. One transaction manager. One rollback. Done.

Across multiple services? Each has its own database. No shared ACID. No shared rollback. You can't just press ROLLBACK and have everyone undo. Each business—each service—commits independently. You're the only one with the full picture. And you're not a transaction manager. You're a human. Or in software, you're a caller. Making HTTP requests. Hoping they all succeed. That's why distributed transactions are hard.

---

## Another Way to See It

Think of it like a relay race. Runner one finishes. Runner two finishes. Runner three drops the baton. But runner one and two already crossed their segments. You can't "undo" their run. You have to send someone back. Tell them to un-run. It's messy. It's manual. And in software, with services spread across networks, it gets worse. One service commits. Another fails. You're left holding partial state—and no magic UNDO button.

---

## Connecting to Software

**Why is it hard?** Four reasons.

**One:** No single transaction manager. Each service is independent. Its database, its rules. Nobody has a global view.

**Two:** Each service has its own DB. No shared ACID. MySQL here. PostgreSQL there. Kafka somewhere else. They don't talk in transactions.

**Three:** The network can fail between steps. Service A commits. The network dies. Service B never gets the call. Or gets it twice. Partial failures everywhere.

**Four:** Partial failures. A and B succeeded. C failed. Now what? Manual cleanup? Error-prone. Race conditions. Duplicate compensations. Nightmares.

**The naive approach:** Just call service A, then B, then C. Simple. Clean. Linear. What if C fails after A and B succeeded? You have inventory reserved. Payment charged. But no order created. Manual cleanup? Good luck. Who does it? When? What if the retry runs and creates the order, but the cleanup also runs? Race conditions. Duplicate work. That's not a solution. That's a liability. And it gets worse with retries. What if A succeeded, B failed, and your caller retried from the beginning? Now A runs twice. Unless you build idempotency everywhere. Distributed transactions force you to think about every failure mode. From day one.

---

## Let's Walk Through the Diagram

```
    NAIVE APPROACH (DANGEROUS)

    [Order Service] → [Inventory] → [Payment] → [Shipping]
         ✓                ✓            ✓           ✗ FAILS

    Result: Inventory reserved. Payment charged. No shipment.
    Customer furious. Money gone. Stock locked. Manual fix.
```

The diagram shows: one failure, and the whole chain breaks. No automatic rollback. Each step that succeeded stays committed. You're left to fix it by hand.

---

## Real-World Examples (2-3)

**Example 1: E-commerce checkout.** Reserve inventory in Service A. Charge payment in Service B. Create order in Service C. What if C fails? Payment succeeded. Order doesn't exist. Customer paid. No record. Refund? How? When? Without a strategy, you're in trouble.

**Example 2: Travel booking.** Flight. Hotel. Car. Three services. Book flight—success. Book hotel—success. Book car—sold out. Now you cancel flight and hotel. Each has different cancellation rules. Different APIs. Different timelines. Distributed coordination, manually orchestrated.

**Example 3: Banking transfers.** Debit account A. Credit account B. Two separate systems. Debit succeeds. Network fails before credit. Money vanishes from A. Never arrives at B. Or: debit succeeds, credit succeeds, but the confirmation times out. Client retries. Same request. Idempotency? Maybe. Maybe not. Double credit? Possible. Distributed transactions make every step a risk. Every network hop. Every timeout. A design decision. Not an afterthought.

---

## Let's Think Together

**E-commerce checkout: reserve inventory (Service A), charge payment (Service B), create order (Service C). Payment succeeds. Order creation fails. Now what?**

You have money. No order. Inventory still reserved. Options: (1) Compensate: refund payment, release inventory. (2) Retry order creation. (3) Manual intervention. The right answer depends on your system. But without a pattern—SAGA, 2PC, or something else—you're guessing. And guessing in production is expensive.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup built "quick" microservices. Order service. Payment service. Inventory service. No distributed transaction design. "We'll just call them in sequence." One night: payment charged 10,000 times. Order creation failed. Retry logic kicked in. Same payment ID. Idempotency? None. Result: 10,000 duplicate charges. One customer. One order. Refunds took weeks. The lesson: naive sequencing plus retries equals disaster. Plan for failure. Always.

---

## Surprising Truth / Fun Fact

Google Spanner claims "globally distributed ACID transactions." How? Massive engineering. GPS clocks. Atomic clocks. TrueTime. Synchronized timestamps across data centers. Millions of dollars in infrastructure. They solved it. For most of us? Distributed transactions stay hard. We use patterns instead: SAGA, 2PC, eventual consistency. Know the problem. Choose the right tool. And never assume "it'll work." Test failure scenarios. Simulate network partitions. Retries. Partial commits. Build for reality. Not for the happy path.

---

## Quick Recap (5 bullets)

- **Distributed transaction** = multiple operations across multiple services/DBs that must all succeed or all fail.
- **Why hard:** No single transaction manager, independent services, network failures, partial commits.
- **Naive approach fails:** Sequential calls with no rollback strategy lead to inconsistent state.
- **Real impact:** E-commerce, travel, banking—all face this. Plan for failure from day one.
- **Solutions exist:** 2PC, SAGA, eventual consistency. We'll cover them next.

---

## One-Liner to Remember

**Distributed transactions are hard because there's no shared UNDO button. Each service commits alone. Plan for partial failure—or pay the price.**

---

## Next Video

So what do we do? Two-phase commit. A protocol that tries to make everyone agree before anyone commits. It works. But it hurts. Why? That's our next video. See you there.
