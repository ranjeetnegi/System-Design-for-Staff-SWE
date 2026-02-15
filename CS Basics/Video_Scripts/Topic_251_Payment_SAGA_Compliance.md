# Payment System: SAGA and Compliance

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Imagine buying a house. You're excited. The loan is approved. Money is transferred. Title is in your name. And then—step four fails. Insurance says no. You're stuck. You can't just walk away. You have to UNDO everything. Give back the title. Return the money. Cancel the loan.

That chaos? That's what happens in payment systems every single day. And the pattern that fixes it—SAGA—plus the rules that govern it—compliance—are what keep your money safe. Let's dive in.

---

## The Story

You're buying a house. Five steps, in order.

Step one: Loan approved. The bank says yes.

Step two: Down payment transferred from your account to escrow.

Step three: Title transferred. The house is legally yours—on paper.

Step four: Insurance purchased. Homeowner's insurance, mandatory.

Step five: Keys handed over. You move in.

Now here's the nightmare. Step four fails. Insurance company denies you. Maybe they found something in the inspection. Whatever the reason, the deal falls apart.

You can't just ignore it. You can't leave the money in escrow. You can't keep the title. You MUST undo steps three, two, and one. In reverse order. Return the title. Refund the down payment. Cancel the loan approval.

That's SAGA in payments. A sequence of steps. Each step has a compensating action—an undo—if something later fails.

---

## Another Way to See It

Think of a domino chain. You knock the first one. Then the second. Third. Fourth. But the fifth domino is blocked. It won't fall.

What do you do? You can't leave the first four lying down. You have to pick them back up. One by one, in reverse. That's compensation.

In software, SAGA is the same idea. Charge the card. Update inventory. Send the receipt. Update analytics. If step three fails—inventory update breaks—you don't leave the card charged and the customer with nothing. You compensate. Refund the card. Put inventory back. In order.

---

## Connecting to Software

In a real payment system, you might have:

1. Charge the card (payment gateway).
2. Update inventory (database).
3. Send receipt (notification service).
4. Update analytics (data warehouse).

Each step talks to a different system. Each can fail. Network timeout. Database deadlock. Third-party API down.

SAGA says: each step has a compensating action. If step two fails, compensate step one. Refund the card. If step three fails, compensate steps two and one. Put inventory back. Refund the card.

The key is idempotency. Every operation—charge, refund, inventory update—must be idempotent. If you retry it, it has the same effect as doing it once. No double charges. No double refunds. Payment systems live and die by idempotency keys.

---

## Let's Walk Through the Diagram

```
User buys product
        |
        v
+-------------------+     success      +-------------------+
|   Charge Card     | ---------------->| Update Inventory  |
+-------------------+                  +-------------------+
        |                                      |
        | fail                                 | fail
        v                                      v
+-------------------+                  +-------------------+
| Compensate: Refund|                  | Compensate:       |
+-------------------+                  | - Restore stock   |
                                      | - Refund card     |
                                      +-------------------+
        |
        v
+-------------------+     success      +-------------------+
|   Send Receipt    | ---------------->| Update Analytics  |
+-------------------+                  +-------------------+
```

Each forward step can trigger compensation of all previous steps if it fails. The SAGA coordinator tracks state and orchestrates forward moves and backward rolls. In choreography-based SAGA, each service emits events; in orchestration-based, a central coordinator calls each service and tracks progress. Both work—orchestration gives you a clear picture of the flow; choreography is more loosely coupled but harder to debug when things go wrong.

---

## Real-World Examples (2-3)

**Stripe:** Uses idempotency keys on every charge. Same key, same request—always the same result. Retry a failed charge? No double billing. The key makes it safe.

**Uber Eats:** Order placed → payment charged → restaurant notified → driver assigned. If the restaurant rejects the order, compensation: refund, cancel driver assignment. SAGA in action.

**Amazon:** Add to cart → reserve inventory → charge on checkout → ship. If shipping fails, compensation: refund, release inventory. You've seen this—order cancelled, money back. That's SAGA working. The receipt step might fail—email down—but you still get your product. Non-critical steps can be eventually consistent. Payment and inventory? Must compensate. Notification? Can retry later.

**Banking wire transfer:** Initiate → debit source account → credit destination → confirm. If credit fails (account closed, invalid), compensate: credit back source. The money never "disappears." SAGA in high-stakes finance. Every step logged. Every compensation auditable. Compliance and SAGA go hand in hand.

---

## Let's Think Together

**Question:** User buys a product. Card is charged. Inventory update fails. How does the SAGA compensate?

**Answer:** The SAGA coordinator detects the failure. It triggers the compensating action for step one: refund the card. The customer gets their money back. Inventory stays as it was—no sale. The system remains consistent. The user might see "payment failed" or "order could not be completed." But they're not charged for nothing.

---

## What Could Go Wrong? (Mini Disaster Story)

Picture this. An e-commerce site charges a customer's card. Inventory update fails. The SAGA tries to compensate—refund. But the refund service is down. The SAGA retries. And retries. Meanwhile, the customer sees a charge on their statement. No product. No refund.

Support is flooded. Social media explodes. "They stole my money!" The refund eventually goes through—maybe hours later. But trust is damaged.

The lesson: compensation must be as reliable as the forward steps. Retry logic. Dead letter queues. Alerts when compensation fails. SAGA only works if UNDO is bulletproof.

---

## Surprising Truth / Fun Fact

GDPR says: users have the right to erasure. Delete my data. But financial regulations say: keep transaction records for seven years. Audit trail. Tax purposes. Law enforcement.

These requirements CONFLICT. You can't delete a user's payment history if the law says you must keep it. Most systems solve this by keeping financial data in a separate, compliance-controlled store. User profile? Deletable. Transaction log? Retained. The art of compliance is managing these contradictions.

---

## Compliance: The Rules Nobody Talks About

PCI-DSS: never store raw card numbers. Tokenize. Encrypt. If you touch card data, you're in scope. Huge burden.

SOX: financial audit trail. Every transaction logged. Who did what, when. Immutable. Tamper-proof.

Data retention: seven years for financial records in many jurisdictions. Right to erasure vs. right to audit. Engineering meets law.

---

## Quick Recap (5 bullets)

- **SAGA** = sequence of steps, each with a compensating action (undo) when a later step fails
- **Idempotency keys** = every payment operation must be retry-safe; no double charges
- **PCI-DSS** = don't store card numbers in plain text; tokenize and encrypt
- **Compliance conflict** = GDPR (right to erasure) vs. financial retention (keep 7 years)
- **Compensation reliability** = UNDO steps must be as robust as forward steps

---

## One-Liner to Remember

**SAGA in payments: charge, update, send—and if anything fails, undo in reverse, with idempotency and compliance as your guardrails.**

---

## Next Video

Up next: Media pipelines. How does YouTube serve your 4K video in ten different qualities in minutes? Storage, transcoding, and the massive orchestration behind it.
