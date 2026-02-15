# SAGA Pattern: Idea and When to Use

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Stop 1: hotel booked. Stop 2: car rented. Stop 3: museum closed. Your road trip hits a wall. But you don't need a global coordinator to fix it. Cancel the car. Cancel the hotel. Each step has an undo. You run backward. That's not just travel logic. That's SAGA.

---

## The Story

Picture a road trip. Five stops planned. Stop 1: book a hotel. Done. Stop 2: book a car rental. Done. Stop 3: book museum tickets. You arrive. "Sorry, we're closed for renovation." Failure. Now what? You don't call a global "trip coordinator" to roll back the universe. You don't have a magic UNDO that reverses time. You just undo. Cancel the car rental. Call. "I'd like to cancel reservation 456." Done. Cancel the hotel. Same. Each step had a forward action. Each has a compensating action. No global lock. No 2PC. No coordinator holding everyone in sync. Just: do each step. If one fails, run compensations backward. Reverse order. That's SAGA. Simple in concept. Complex in practice. But it works. At scale. Across services. Across teams.

---

## Another Way to See It

Think of stacking blocks. You stack block 1. Block 2. Block 3. Block 4 falls. You don't explode the whole tower. You carefully remove block 3. Then 2. Then 1. Reverse order. Each removal is a compensation—a correction. The tower returns to a stable state. Not necessarily empty. But consistent. That's SAGA. Sequential forward steps. Sequential backward compensation when something breaks.

---

## Connecting to Software

**SAGA** = a sequence of local transactions. Each has a compensating transaction. No distributed lock. No 2PC. Each service does its own thing. In its own database. Atomic locally. Not atomic globally.

**Forward flow:** T1 → T2 → T3 → T4. Each T is a local transaction. Commit. Move on.

**When T4 fails:** Run compensations backward. C3 (undo T3) → C2 (undo T2) → C1 (undo T1). Reverse order. Each compensation is a business-level "undo"—refund, cancel, release. Not a database ROLLBACK. A corrective action.

**When to use SAGA:** Microservices without a shared database. Long-running transactions that span minutes or hours—not milliseconds. When 2PC is too expensive, too blocking, or your infrastructure doesn't support it. When you can define compensations for every step. When eventual consistency is acceptable. SAGA doesn't give you ACID. It gives you "eventually consistent with compensation." The system might be briefly inconsistent. But it recovers. That's the trade-off. For many business processes, it's good enough. Better than blocking. Better than manual cleanup.

---

## Let's Walk Through the Diagram

```
    SAGA: FORWARD AND COMPENSATION

    Forward:   T1 -------> T2 -------> T3 -------> T4
                 ✓           ✓           ✓           ✗ FAIL

    Compensate:            C3 <------- C2 <------- C1
                           undo T3     undo T2     undo T1

    Order: Do C3 first. Then C2. Then C1. Reverse of forward.
```

The diagram shows: failure triggers backward compensation. No global coordinator. Each service runs its own compensation. The system reaches a consistent—if not original—state.

---

## Real-World Examples (2-3)

**Example 1: Flight booking.** Reserve seat → charge card → send confirmation. If confirmation fails, do you compensate? Refund? Cancel reservation? Depends. Sometimes confirmation failure is not "real" failure—retry. Maybe the email service was slow. Retry in 30 seconds. Sometimes it is. Card declined. No seat. Compensate. SAGA makes you think: what's the compensating action for each step? And when do you retry vs compensate? Design decision. Business decision. Not just technical. The pattern forces clarity. That's valuable.

**Example 2: Order placement.** Create order → reserve inventory → charge payment → ship. If payment fails: release inventory, cancel order. If ship fails: refund payment, release inventory, cancel order. Each compensation is a business operation. Not a DB rollback.

**Example 3: Travel package.** Book flight, hotel, car. Hotel full? Compensate: cancel flight, release car hold. Reverse order. Each service has its own cancel API. SAGA orchestrates the sequence. Real-world: Booking.com, Expedia, Kayak. They all do this. Multiple providers. Multiple APIs. No 2PC across airlines and hotels. SAGA. Compensations. It's the industry pattern for travel. And for many e-commerce flows. Proven at scale.

---

## Let's Think Together

**Flight booking SAGA: reserve seat → charge card → send confirmation. Card charge succeeds. Confirmation email fails. Is this a real failure? Should you compensate?**

Tricky. The customer paid. They have a seat. The only failure is communication. Compensating would mean: refund + cancel seat. That punishes the customer for an email glitch. Better: retry confirmation. Maybe store the event, reprocess. Compensation is for business failures. Email failure might not be one. Design your compensations around business impact.

---

## What Could Go Wrong? (Mini Disaster Story)

A team built a SAGA for orders. Forgot to make compensations idempotent. Payment failed. Compensation ran. Refund issued. Retry happened—same compensation ran again. Double refund. Customer got money twice. Company lost revenue. Lesson: compensations must be safe to retry. Idempotency. Check "did I already refund this?" before refunding.

---

## Surprising Truth / Fun Fact

SAGA was coined in a 1987 paper by Hector Garcia-Molina. Database research. The idea: long transactions as sequences of smaller ones with compensations. Microservices brought it back. Old concept. New context. Still relevant. The problem it solved in 1987—long-running transactions in databases—is the same problem we have today across services. Scale changed. Technology changed. The pattern didn't. Good design endures.

---

## Quick Recap (5 bullets)

- **SAGA** = sequence of local transactions + compensating transactions for rollback.
- **No 2PC:** No distributed locks. Each service commits locally.
- **Compensation** = business-level undo (refund, cancel, release). Not DB rollback.
- **Order:** Compensate in reverse. If T3 fails, run C3, C2, C1.
- **Use when:** Microservices, long transactions, 2PC too costly.

---

## One-Liner to Remember

**SAGA: Do steps forward. If one fails, compensate backward. No global lock. Each step knows how to undo itself.**

---

## Next Video

But how do you coordinate a SAGA? Choreography—everyone reacts to events? Or orchestration—one boss tells everyone what to do? Two designs. Different trade-offs. That's next. See you there.
