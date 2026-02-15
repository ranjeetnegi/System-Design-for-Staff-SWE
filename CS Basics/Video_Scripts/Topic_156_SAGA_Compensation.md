# Compensation in SAGA: Rolling Back Without 2PC

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You bought a non-refundable flight. Can you "undo" the purchase? No. But you can do something else. Buy a new ticket. Get a credit note. That's not rollback. That's compensation. A corrective action. Brings the system to an acceptable state. In SAGAs, every step needs one of those.

---

## The Story

You bought a non-refundable flight ticket. The database can't "rollback" that row. The money left your account. The airline has it. You can't magically undo. But you CAN do something else. Request a credit note. Or buy a new ticket for another date. That's compensation. Not a true undo. A business-level fix. The system might not return to the exact original state. But it reaches a consistent, acceptable state. In SAGAs, each step defines its own compensation. Not magical rollback. Real-world correction.

---

## Another Way to See It

Think of sending an email. You sent it. It's in their inbox. You can't "unsend." But you can send a follow-up: "Please ignore my previous email." That's compensation. The original email exists. But you've corrected the situation. In software: you can't un-charge a credit card. But you can issue a refund. You can't un-reserve a hotel room with a simple ROLLBACK. But you can call the cancel API. Compensation is the business equivalent of "fixing it."

---

## Connecting to Software

**Compensation ≠ rollback.** Rollback is transactional. Database says: "Forget that INSERT." Poof. Gone. Compensation is semantic. You can't un-send an email. But you can send "Please ignore." You can't un-charge a card. But you can refund. Each compensation is a new operation. It has side effects. It can fail too. Design for that.

**Design challenges:** (1) **Idempotency.** Compensation might run twice. Retries. Duplicate events. Make it safe. "Did I already refund this?" Check. Then act. Never assume "this runs once." It might run three times. Design for it. (2) **Partial state.** Original step might have partially completed. Timeout mid-way. Compensation must handle that. "Did we reserve or not?" Check. Act accordingly. Compensation is not a simple inverse. It's a corrective action. Handle edge cases. (3) **Semantic rollback.** The system may not return to EXACT original state. But to a consistent state. Document what "consistent" means. "Refund issued" is consistent. "Email unsent" might be impossible. "Cancellation email sent" is the best we can do. That's compensation. Business-level. Not perfect. Good enough.

---

## Let's Walk Through the Diagram

```
    COMPENSATION vs ROLLBACK

    ROLLBACK (single DB):
    BEGIN; INSERT x; INSERT y; FAIL; ROLLBACK;
    → x and y never existed. Clean.

    COMPENSATION (SAGA):
    Service A: reserve room ✓
    Service B: charge card ✓
    Service C: send email ✓
    Service D: FAIL
    → Compensation: un-send email? Can't.
                → Send "cancellation" email. ✓
                → Refund card ✓
                → Cancel reservation ✓
    State: not "original" but consistent.
```

Compensation is business logic. Not database magic. Each service knows how to "fix" what it did.

---

## Real-World Examples (2-3)

**Example 1: Hotel booking.** Forward: reserve room, charge card, send confirmation. Compensation: cancel reservation, refund card, send "booking cancelled" email. The "cancel confirmation" email is compensation for "send confirmation." You can't delete the first email. It's sent. It's in their inbox. You correct with a second. "Your booking has been cancelled." Now the customer has both emails. Confusing? Maybe. But consistent. They know the final state. That's compensation. Not perfect. Good enough. Business-level fix. Not technical perfection.

**Example 2: Order + inventory.** Forward: create order, reserve inventory. Fail at payment. Compensation: cancel order, release inventory. Release inventory is an API call. Not ROLLBACK. The reservation service runs its own logic. Maybe it had a timeout. Maybe the reserve partially failed. Compensation must be resilient. Handle "did we reserve or not?" Check. Then release. Or don't. Compensation is code. It has to handle reality. Not just the happy path. Test it. Same as any critical path. Compensations fail too. Retry. Alert. Don't assume they always work. Design for failure. In the failure handler.

**Example 3: Subscription.** Forward: create subscription, charge first month, grant access. Fail at "grant access." Compensation: refund, cancel subscription. Grant access might have partially run. Compensation: revoke access. Handle partial state.

---

## Let's Think Together

**Hotel reservation SAGA: room reserved, payment charged, confirmation sent. Payment needs refund. How do you compensate the confirmation email?**

You can't "unsend" it. Options: (1) Send a "booking cancelled" follow-up email. Customer gets two emails. Consistent message. (2) Don't "compensate" the email at all—treat it as non-critical. The refund and cancellation are the real compensations. Email is just notification. Decide: is the email part of the transactional state or just a side effect? Often: refund + cancel are enough. Email is best-effort correction. Design for your domain.

---

## What Could Go Wrong? (Mini Disaster Story)

A payment SAGA. Charge succeeded. Order creation failed. Compensation: refund. Refund ran. Then a bug: retry. Refund ran again. No idempotency check. Double refund. Customer got money twice. Support tickets. Finance confused. Lesson: every compensation must be idempotent. "Transaction ID X already refunded." Skip. Safe. Always.

---

## Surprising Truth / Fun Fact

Some systems use "compensation" as a first-class concept. Microsoft's Compensating Transaction (COM+) in the 90s. Saga pattern in practice. The idea is old. Microservices made it popular again. Compensation isn't new. It's proven. Design it well.

---

## Quick Recap (5 bullets)

- **Compensation ≠ rollback.** Business-level corrective action. Refund, cancel, revoke.
- **Idempotent:** Compensation can run multiple times. Must be safe. Check before act.
- **Semantic:** System reaches consistent state. Not necessarily original state.
- **Design:** Each forward step needs a defined compensation. Handle partial state.
- **Failure:** Compensations can fail. Need retry. Need alerts. Compensation is not "easy."

---

## One-Liner to Remember

**Compensation: you can't undo. You fix. Refund instead of un-charge. Cancel instead of un-reserve. Design every step with its correction.**

---

## Next Video

SAGAs often publish events. Order created. Payment done. But what if you save to the database and fail to publish? Data in DB. Event lost. Systems out of sync. The outbox pattern solves this. Reliable event publishing. That's next. See you there.
