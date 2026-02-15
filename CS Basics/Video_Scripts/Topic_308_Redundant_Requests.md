# Redundant Requests: When to Dedupe

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You text your friend "Happy Birthday!" Your phone shows "not delivered." You send again. And again. Your friend gets three "Happy Birthday!" messages. Annoying but harmless. Now imagine it's a payment: "Transfer fifty thousand rupees." Three times. Not harmless. Some duplicates are embarrassing. Some are expensive. **When** to deduplicate depends on the cost of the duplicate.

## The Story

Not every duplicate is created equal. A duplicate "Add to Cart" might add the item twice. Annoying. User removes one. A duplicate "Place Order" might charge twice, ship twice, drain inventory twice. Disaster. A duplicate "Read Article" does nothing. GET is idempotent. So when do you dedupe?

**Always dedupe**: Payments. Orders. Inventory changes. State-changing operations where the cost of running twice is high. Money. Data corruption. User trust. These need idempotency keys, dedup windows, or both.

**Sometimes dedupe**: Notifications. "Your order shipped." Two emails? Annoying. User rolls their eyes. But not catastrophic. Analytics events. Slight overcount? Acceptable for many use cases. Logging. Duplicate log lines? Noise. Not critical. You might dedupe if it's easy. Or skip if the cost of implementation outweighs the benefit.

**Don't dedupe**: Read requests. GET. Idempotent by nature. Health checks. Metrics polling. No harm in running twice. Deduplication adds complexity for zero gain.

## Another Way to See It

Like locking your door. You lock it when you leave. High cost if someone gets in. You don't lock your pencil drawer. Low cost. Effort should match the risk. Dedup when the cost of a duplicate is high. Skip when it's trivial. And sometimes the cost depends on scale. One duplicate notification? Annoying. A million duplicate notifications in an outage? Your notification service melts. Your email provider flags you as spam. Cost scales. Design for your scale.

## Connecting to Software

How to decide? Ask: **"What's the worst that happens if this request runs twice?"**

- Payment: double charge. Dedupe.
- Order: double order. Dedupe.
- Add to cart: double add. User fixable. Maybe dedupe with a short window, maybe not.
- Place order: double order. Dedupe.
- Send email: duplicate email. Annoying. Depends on volume. High-volume transactional email? Dedupe. Marketing email? Probably not worth it.
- Log event: duplicate log. Who cares? Skip.

The decision is economic. Cost of duplicate vs cost of implementing dedup. Sometimes the cost of a duplicate is hard to quantify. "Two 'order shipped' emails" — user annoyance. Hard to put a number on. "Double payment" — easy. Refund cost, support cost, trust cost. When in doubt for money or orders: dedupe. When in doubt for reads or low-impact actions: skip. Your time has value. Spend it where it matters. And remember: dedup has its own cost. Storage for keys. Lookup latency. Key design (wrong key = wrong dedup). Don't add complexity everywhere. Add it where the risk justifies it. A simple rule of thumb: if processing twice costs money or violates a business rule, dedupe. If processing twice is merely redundant, consider skipping.

## Let's Walk Through the Diagram

```
  Request Type          Duplicate Cost        Dedupe?

  Place Order           $$$$ (money, trust)   YES
  Process Payment       $$$$ (money, legal)   YES
  Update Inventory      $$$ (wrong stock)    YES
  Add to Cart           $ (user removes)      MAYBE
  Send Notification    $ (annoying)         MAYBE
  Analytics Event       ~0 (slight overcount) NO (often)
  GET /product/123      0 (idempotent)       NO
```

## Real-World Examples (2-3)

- **Stripe**: Dedupes all payment-related operations. Idempotency keys. No double charges.
- **Uber**: "Request ride." Dedupe. One errant tap shouldn't book two rides.
- **News app**: "Mark as read." Duplicate? Same result. Idempotent. No need to dedupe specially.
- **Chat**: "Send message." Could dedupe at application layer to avoid duplicate bubbles. Or rely on client-side dedup—client generates message ID, server rejects duplicate IDs. Context matters. For chat, duplicate message is annoying but not catastrophic. Many systems accept best-effort.

## Let's Think Together

**User clicks "Add to Cart" twice rapidly. Should you dedupe? What about "Place Order"?**

Add to Cart: debatable. Duplicate adds the item twice. User sees quantity 2. They can fix it. Deduping would require a key ("add-to-cart-for-session-X-item-Y") and a short window. Some sites do it. Many don't. Place Order: absolutely dedupe. Duplicate = two orders, two charges. Idempotency key. No question.

## What Could Go Wrong? (Mini Disaster Story)

You dedupe everything. Great. Conservative. Safe. But your dedup layer has a bug. Sometimes it incorrectly flags a legitimate new request as a duplicate. User places Order A. Then Order B (different items). Your system thinks B is a duplicate of A. Rejects B. User thinks their order failed. They retry. Gets rejected again. Support nightmare. Dedup is powerful. It can also block valid requests if your key design is wrong. Each logical request needs a unique key. Order A and Order B are different. Keys must reflect that. And the key scope matters. "One key per user per day" is wrong for orders—user might place 5 orders in a day. "One key per order placement attempt" is right. Client generates when user clicks Place Order. Attach to that request. Retries reuse it. New order? New key. Design the key to match the unit of idempotency.

## Surprising Truth / Fun Fact

Many systems over-dedupe and under-dedupe. Over: they add complex dedup for read-heavy endpoints. Waste of engineering time. Under: they skip dedup for payments. "Our network is reliable." Until it isn't. One retry. Double charge. Refund. Angry customer. The best approach: classify your operations early. High-cost duplicates? Dedupe. Low-cost? Don't bother. Document the decision. Put it in your API design doc. Future you—and future teammates—will thank you when they're debugging "why did we charge twice?" and the answer is "we didn't implement idempotency."

---

## Quick Recap (5 bullets)

- Always dedupe: payments, orders, inventory, high-cost state changes—where duplicate = money or trust lost
- Sometimes dedupe: notifications, analytics—cost is low, benefit is marginal
- Don't dedupe: reads (idempotent), health checks, metrics
- Ask: "What's the worst if this runs twice?" Match effort to risk
- Wrong key design can block valid requests—each logical request needs a unique key; scope matters (per order, not per user)

## One-Liner to Remember

*Dedupe when the duplicate costs more than the dedup.*

Not everything needs it. Classify. High-cost operations get idempotency keys. Low-cost gets best-effort or nothing. Pragmatism over paranoia. A simple spreadsheet of "dedupe or not" per endpoint can save hours of design debates. Document it. Ship it. Review it when you add new endpoints.

---

## Next Video

Up next: Bulkheads—how ships stay afloat when one compartment floods. Same idea in software. See you there.
