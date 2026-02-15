# Chapter 43: Payment Flow

---

# Introduction

When a user clicks "Pay $49.99," they expect one thing: the money leaves their account once, the merchant gets paid, and they receive a confirmation. That single click triggers an intricate flow touching authorization, capture, ledger recording, webhook delivery, and reconciliation. A payment flow is the system that orchestrates this sequence reliably—ensuring money moves correctly even when networks partition, services crash, and third-party processors return ambiguous responses.

I've built payment flows that processed $2M/day across tens of thousands of transactions, debugged an incident where an ambiguous gateway timeout caused 340 customers to be charged twice (total double-charge: $17K, resolved in 4 hours, post-mortem lasted a week), and designed idempotency layers that survived a 20-minute payment processor outage without a single duplicate or lost charge. The lesson: a payment system that occasionally loses a transaction is bad, but one that occasionally charges someone twice is catastrophic—because money is trust, and trust is non-recoverable.

This chapter covers a payment flow as a Senior Engineer owns it: authorization, capture, idempotency, ledger recording, reconciliation, refunds, and the operational reality of keeping money correct at scale.

**The Senior Engineer's First Law of Payments**: Money must never be created or destroyed by a bug. Every cent entering the system must have a corresponding debit, every cent leaving must have a corresponding credit, and the ledger must always balance. If it doesn't, stop everything and figure out why.

**Staff addition**: A Staff Engineer designs for blast radius and cross-team ownership. When the ledger is wrong, who is paged? Payment team or Finance? When the processor fails, which teams need to coordinate? Payment correctness is not just a technical problem—it's an organizational one. Document contracts, define failure boundaries, and accept risks explicitly.

---

# Part 1: Problem Definition & Motivation

## Mental Model & One-Liners

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PAYMENT FLOW: CORE MENTAL MODEL                           │
│                                                                             │
│   A payment flow is a STATE MACHINE + LEDGER + RECONCILIATION:              │
│   • State machine: Every status transition is explicit and auditable         │
│   • Ledger: Double-entry; sum(debits) = sum(credits) always                 │
│   • Reconciliation: Processor is verified against ledger, not vice versa     │
│                                                                             │
│   MEMORABLE ONE-LINERS:                                                      │
│   • "The processor is a dependency, not the source of truth"                 │
│   • "Timeout = UNKNOWN, not FAILED. Check before retry"                      │
│   • "Idempotency keys are deterministic—never timestamps or random"         │
│   • "Infrastructure cost is noise; processor fees are the budget"             │
│   • "Reconciliation is the safety net for everything else"                    │
│   • "Double-charge destroys trust; lost payment loses revenue"                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What Is a Payment Flow?

A payment flow accepts a user's intent to pay, validates the payment method, authorizes the charge with an external payment processor, captures the funds, records the transaction in an internal ledger, and delivers confirmation to the user and downstream systems. It ensures that money moves correctly, exactly once, and that every state transition is auditable.

### Simple Example

```
PAYMENT FLOW OPERATIONS:

    INITIATE:
        User clicks "Pay $49.99" for Order #1234
        → Frontend sends: POST /payments {order_id: 1234, amount: 4999, currency: "USD",
                                           payment_method: "card_tok_abc", idempotency_key: "order-1234-pay"}
        → Payment Service validates amount, checks order status, creates payment record
        → Status: "created"

    AUTHORIZE:
        Payment Service → Payment Processor (Stripe/Adyen/Braintree)
        → Request: "Authorize $49.99 on card ending 4242"
        → Processor response: {authorization_code: "AUTH_789", status: "authorized"}
        → Funds reserved on customer's card (not yet captured)
        → Status: "authorized"

    CAPTURE:
        After order confirmed/shipped:
        → Payment Service → Processor: "Capture AUTH_789 for $49.99"
        → Processor response: {capture_id: "CAP_456", status: "captured"}
        → Money transferred from customer to merchant
        → Status: "captured"

    RECORD:
        Ledger entry:
        → DEBIT  customer_receivable  $49.99
        → CREDIT revenue              $49.99
        → Immutable, append-only, auditable

    CONFIRM:
        → Webhook to Order Service: "Payment captured for Order #1234"
        → Email receipt to customer
        → Status: "completed"
```

## Why Payment Flows Exist

Money requires stronger guarantees than any other data in your system. An incorrect user profile is annoying; an incorrect charge is a legal and trust violation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY BUILD A PAYMENT FLOW?                                │
│                                                                             │
│   WITHOUT A STRUCTURED PAYMENT FLOW:                                        │
│   ├── Direct API call to Stripe in the checkout handler (no retry, no       │
│   │   idempotency, no ledger)                                               │
│   ├── Gateway timeout: Did the charge succeed? Unknown. User retries.       │
│   │   Double charge. $49.99 × 2 = angry customer + chargeback.              │
│   ├── No internal ledger: "How much revenue did we collect today?"          │
│   │   Answer: "Ask Stripe." (single source, unverifiable)                   │
│   ├── Refund: Manual Stripe dashboard action (no audit trail, no            │
│   │   reconciliation)                                                       │
│   ├── Partial failure: Order created, payment failed. Orphaned order.       │
│   │   Or: Payment captured, order creation failed. Charged but no product.  │
│   └── Compliance: No audit log. PCI auditor asks "show me every charge      │
│       and its outcome for the last 90 days." Answer: "We can't."            │
│                                                                             │
│   WITH A STRUCTURED PAYMENT FLOW:                                           │
│   ├── Idempotent: Retry is safe; double-click ≠ double-charge               │
│   ├── Auditable: Every state transition logged with timestamp and actor     │
│   ├── Reconcilable: Internal ledger matches processor records daily         │
│   ├── Recoverable: Ambiguous responses → safe recovery without duplicates   │
│   ├── Refundable: Programmatic refund with matching debit/credit            │
│   └── Observable: Revenue, failure rate, processor latency on dashboards    │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   A payment flow is NOT a database transaction. It spans multiple           │
│   systems (your service, the payment processor, the bank) that cannot       │
│   participate in a single ACID transaction. You must build correctness      │
│   from idempotency, state machines, and reconciliation—not from             │
│   distributed locks.                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Problem 1: The Ambiguous Response Problem

```
THE CORE CHALLENGE:

You send "Authorize $49.99" to the payment processor.
Three outcomes:

    1. SUCCESS: {status: "authorized", auth_code: "ABC"}
       → Clear. Record authorization. Proceed to capture.

    2. FAILURE: {status: "declined", reason: "insufficient_funds"}
       → Clear. Tell user. No money moved.

    3. TIMEOUT / NETWORK ERROR: [no response]
       → Did the charge succeed or not?
       → If you retry: Risk double-charge
       → If you don't retry: Risk lost payment (order goes unfulfilled)
       → If you ask the processor: "Did AUTH for idempotency_key X succeed?"
         → But what if THAT request also times out?

THIS IS THE HARDEST PROBLEM IN PAYMENTS.

Every other design decision flows from this:
    - Idempotency keys: Ensure retries don't create duplicates
    - State machine: Track exactly where the payment is in its lifecycle
    - Reconciliation: Detect and correct mismatches
    - Conservative defaults: When in doubt, do NOT charge the customer
```

### Problem 2: The Double-Charge Problem

```
DOUBLE-CHARGE SCENARIO:

    T=0: User clicks "Pay"
    T=1: Payment service sends authorize to processor
    T=6: Timeout (5-second threshold). No response received.
    T=7: Payment service retries authorize (different request ID!)
    T=8: Processor processes FIRST request (network was slow, not down)
         → auth_code: AUTH_001
    T=9: Processor processes SECOND request (new request, new charge)
         → auth_code: AUTH_002
    T=10: Payment service receives AUTH_002 response
    T=11: Payment service receives AUTH_001 response (delayed)

    Result: Customer authorized TWICE for $49.99.
    If both are captured: $99.98 charged. Customer furious.

PREVENTION: Same idempotency_key on both requests.
    Processor sees: "I already processed this idempotency_key → return AUTH_001"
    Second request is a no-op.

    THIS IS WHY idempotency keys are non-negotiable in payments.
```

### Problem 3: The Money Accounting Problem

```
ACCOUNTING CHALLENGE:

    If you only track payments in the processor (Stripe dashboard):
    - How much revenue did we earn yesterday? (Must query Stripe, hope API is up)
    - Did all captured payments match our orders? (No way to verify locally)
    - Is there a discrepancy between what we think we charged and what the
      processor thinks? (Unknown until a customer complains)

    If you maintain an internal ledger:
    - Revenue is a SQL query on YOUR database (always available)
    - Every payment has a matching order (enforced by your system)
    - Daily reconciliation: Compare ledger totals vs processor settlement report
    - Discrepancy? Detected within 24 hours, not 30 days.

PRINCIPLE: The payment processor is a dependency, not the source of truth.
Your internal ledger is the source of truth. The processor is verified against it.
```

---

# Part 2: Users & Use Cases

## User Categories

| Category | Who | How They Use the Payment Flow |
|----------|-----|-------------------------------|
| **End users (customers)** | People buying products/services | Click "Pay," expect single charge and receipt |
| **Order Service** | Internal service creating orders | Initiates payment, awaits confirmation webhook |
| **Finance/Accounting** | Internal team reconciling revenue | Queries ledger, runs daily reconciliation reports |
| **Support team** | Customer support agents | Looks up payment status, initiates refunds |
| **Compliance/Audit** | Auditors reviewing financial records | Inspects payment audit trail, PCI compliance |
| **Payment processor** | Stripe/Adyen/Braintree | Receives authorization/capture requests, sends webhooks |

## Core Use Cases

```
USE CASE 1: SINGLE PAYMENT (Happy Path)
    User pays for an order with a saved card
    → Authorize → Capture → Ledger entry → Confirmation
    Expectation: Complete in < 5 seconds. Single charge. Receipt in email.

USE CASE 2: AUTHORIZATION + DELAYED CAPTURE
    User places order; merchant ships 2 days later
    → Authorize immediately (reserve funds)
    → Capture when order ships (settle funds)
    WHY: Customer should only be charged when value is delivered.
    Authorization expires after 7 days (processor-dependent).

USE CASE 3: REFUND (FULL OR PARTIAL)
    Customer requests refund for damaged item
    → Support agent initiates refund via admin tool
    → Payment Service → Processor: "Refund $49.99 on CAP_456"
    → Ledger: Reverse entry (DEBIT revenue, CREDIT customer_receivable)
    Expectation: Refund reflected in 5-10 business days.

USE CASE 4: PAYMENT FAILURE AND RETRY
    Card declined (insufficient funds)
    → User notified: "Payment failed. Please try another card."
    → User submits different card → new payment attempt
    → Previous authorization voided (if applicable)

USE CASE 5: RECONCILIATION
    Daily automated process:
    → Pull settlement report from processor
    → Compare with internal ledger
    → Flag discrepancies: Missing captures, orphaned authorizations, amount mismatches
    → Alert if discrepancy > $0.01
```

## Non-Goals

```
NON-GOALS (Explicitly Out of Scope):

1. PAYMENT METHOD MANAGEMENT (Wallet)
   Storing, tokenizing, and managing multiple cards/bank accounts.
   That's a payment method service. This system assumes a token is provided.

2. SUBSCRIPTION / RECURRING BILLING
   Scheduled charges, plan management, proration, dunning.
   Different lifecycle, different system. Recurring billing USES this
   payment flow but is not the same system.

3. MULTI-CURRENCY / FX
   Cross-currency conversion, exchange rate management.
   V1: Single currency (USD). Multi-currency adds conversion risk,
   settlement complexity, and regulatory requirements.

4. FRAUD DETECTION
   ML-based fraud scoring, velocity checks, device fingerprinting.
   Separate system that runs BEFORE payment initiation. This system
   assumes the fraud check has already passed.

5. PCI DSS CARD DATA HANDLING
   Storing raw card numbers. We never see them. The payment processor
   handles PCI scope. We use tokenized references only.
```

---

# Part 3: Functional Requirements

## Write Flows

```
FLOW 1: CREATE PAYMENT

    Client → Payment API → Validate → Create Record → Return payment_id

    Steps:
    1. Client sends: {order_id, amount_cents, currency, payment_method_token,
                      idempotency_key}
    2. Validate:
       - Order exists and is in "pending_payment" state
       - Amount matches order total
       - Currency is supported (USD for V1)
       - payment_method_token is non-empty
       - idempotency_key is present and unique (or return existing payment)
    3. Create payment record:
       - payment_id: UUID
       - status: "created"
       - amount_cents, currency, order_id, payment_method_token
       - idempotency_key (unique index)
    4. Return: {payment_id, status: "created"}

    Idempotency: If idempotency_key already exists:
       - Return existing payment (same payment_id, current status)
       - Do NOT create a duplicate

FLOW 2: AUTHORIZE PAYMENT

    Payment Service → Payment Processor → Update Record

    Steps:
    1. Payment Service reads payment record (status must be "created")
    2. Sends authorization request to processor:
       {amount: 4999, currency: "USD", token: "card_tok_abc",
        idempotency_key: "order-1234-auth"}
    3. Processor responds:
       a. authorized: Save auth_code, set status → "authorized"
       b. declined: Set status → "declined", save decline_reason
       c. timeout/error: Leave status as "created", schedule retry
    4. If authorized: Notify Order Service (webhook or event)

    CRITICAL: The processor idempotency_key is DIFFERENT from the
    payment idempotency_key. The processor key ensures retries to the
    PROCESSOR are safe. The payment key ensures retries from the CLIENT
    are safe. Two layers of idempotency.

FLOW 3: CAPTURE PAYMENT

    Order Service triggers → Payment Service → Processor → Ledger

    Steps:
    1. Order Service calls: POST /payments/{payment_id}/capture
    2. Payment Service reads payment record (status must be "authorized")
    3. Sends capture request to processor:
       {auth_code: "AUTH_789", amount: 4999,
        idempotency_key: "order-1234-capture"}
    4. Processor responds:
       a. captured: Set status → "captured", save capture_id
       b. failed: Set status → "capture_failed", save error
       c. timeout: Leave as "authorized", schedule retry
    5. If captured:
       a. Write ledger entry (double-entry: debit + credit)
       b. Notify Order Service: "Payment captured"
       c. Trigger receipt email job

FLOW 4: REFUND PAYMENT

    Support Agent / Automated → Payment Service → Processor → Ledger

    Steps:
    1. Refund request: {payment_id, amount_cents, reason, initiated_by}
    2. Validate:
       - Payment exists and status is "captured"
       - Refund amount <= captured amount - already_refunded amount
       - Refund reason is non-empty
    3. Create refund record: {refund_id, payment_id, amount_cents, status: "created"}
    4. Send refund to processor:
       {capture_id: "CAP_456", amount: 4999,
        idempotency_key: "order-1234-refund-1"}
    5. Processor responds:
       a. refunded: Set status → "refunded", write reverse ledger entry
       b. failed: Set status → "refund_failed", alert
       c. timeout: Schedule retry
    6. Notify: Order Service, customer email
```

## Read Flows

```
FLOW 5: PAYMENT STATUS QUERY

    Client → Payment API → Read Record → Return Status

    Steps:
    1. GET /payments/{payment_id}
    2. Return: {payment_id, order_id, amount_cents, currency, status,
                auth_code, capture_id, created_at, authorized_at, captured_at,
                refunds: [{refund_id, amount, status}]}

    Access control:
    - Customer: Can see own payments (via Order Service, not direct)
    - Support agent: Can see any payment (admin role)
    - Finance: Read-only access to ledger entries

FLOW 6: RECONCILIATION (Daily)

    Scheduled Job → Pull Processor Report → Compare Ledger → Flag Discrepancies

    Steps:
    1. Download settlement report from processor API (CSV/JSON)
    2. For each processor transaction:
       a. Find matching payment in internal ledger (by processor_transaction_id)
       b. Compare: amount, status, capture date
    3. Flag discrepancies:
       - Payment in processor but not in ledger: "orphaned charge"
       - Payment in ledger but not in processor: "missing settlement"
       - Amount mismatch: "amount discrepancy"
    4. Alert if any discrepancy found
    5. Generate reconciliation report for finance team
```

## Behavior Under Partial Failure

```
PARTIAL FAILURE: Processor authorization times out

    Behavior:
    - Payment stays in "created" state (NOT "authorized")
    - Retry scheduler picks it up after 30 seconds
    - Retry with SAME processor idempotency_key (safe: processor deduplicates)
    - If processor was slow (not down): Already authorized; returns cached result
    - If processor was down: Retry gets fresh response

    Recovery:
    - Max 3 retries over 5 minutes
    - If still no response: Status → "authorization_failed"
    - User notified: "Payment could not be processed. Please try again."

    CONSERVATIVE DEFAULT: Do not capture unless authorization is confirmed.
    Unknown state = treat as failed. Customer is not charged.

PARTIAL FAILURE: Capture succeeds at processor but ledger write fails

    Behavior:
    - Money moved at processor (charge is real)
    - Internal ledger doesn't reflect it
    - Reconciliation will catch this within 24 hours
    
    Immediate mitigation:
    - Retry ledger write (transient DB issue)
    - If persistent: Flag payment as "capture_ledger_pending"
    - Alert: "Captured payment without ledger entry"

    WHY this is safe:
    - Money is at the processor (customer IS charged)
    - Ledger is internal (we can fix it)
    - Reconciliation detects and corrects within 24 hours
    - NEVER the reverse: Ledger says charged but processor didn't capture

PARTIAL FAILURE: Order Service webhook delivery fails

    Behavior:
    - Payment captured, ledger written, but Order Service not notified
    - Order stays in "pending_payment" state
    
    Recovery:
    - Retry webhook (3 attempts with exponential backoff)
    - If still failing: Payment Service exposes status API
    - Order Service polls: GET /payments?order_id=1234
    - Reconciliation: "Captured payment without order fulfillment" alert
```

---

# Part 4: Non-Functional Requirements (Senior Bar)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NON-FUNCTIONAL REQUIREMENTS                              │
│                                                                             │
│   LATENCY:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Create payment: P99 < 50ms (local DB write)                        │   │
│   │  Authorize: P99 < 5 seconds (processor dependent, 2-3s typical)     │   │
│   │  Capture: P99 < 5 seconds (processor dependent)                     │   │
│   │  Refund: P99 < 5 seconds (processor dependent)                      │   │
│   │  Status query: P99 < 50ms (local DB read)                           │   │
│   │                                                                     │   │
│   │  WHY: Authorization latency is dominated by the external            │   │
│   │  processor (network round-trip + bank authorization). Our system    │   │
│   │  adds < 100ms overhead on top of processor latency.                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   AVAILABILITY:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Payment creation: 99.95% (must accept payment intent)              │   │
│   │  Authorization: 99.9% (depends on processor; degrade gracefully)    │   │
│   │  Capture: 99.9% (retry-safe; brief delays acceptable)               │   │
│   │  Refund: 99.5% (manual backup via processor dashboard)              │   │
│   │                                                                     │   │
│   │  WHY 99.95% for creation:                                           │   │
│   │  A failed payment creation = lost sale. The customer clicked "Pay"  │   │
│   │  and got an error. They may not retry. Revenue loss.                │   │
│   │                                                                     │   │
│   │  WHY 99.9% for authorization (not higher):                          │   │
│   │  We depend on the processor, which has its own SLA (~99.95%).       │   │
│   │  Our availability cannot exceed our dependency's availability.      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CONSISTENCY:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  STRONG consistency for payment state transitions                   │   │
│   │  - Payment status is a linearizable state machine                   │   │
│   │  - No concurrent transitions on the same payment                    │   │
│   │  - Read-your-write: After capture, status query returns "captured"  │   │
│   │                                                                     │   │
│   │  WHY strong (not eventual):                                         │   │
│   │  Money demands deterministic state. "Payment is authorized AND      │   │
│   │  captured simultaneously" is nonsensical and dangerous. Every       │   │
│   │  read must reflect the latest state.                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DURABILITY:                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Zero payment data loss. Ever.                                      │   │
│   │  - Synchronous replication to standby (no async lag risk)           │   │
│   │  - WAL archived to object storage (point-in-time recovery)          │   │
│   │  - Daily backups with verified restore                              │   │
│   │                                                                     │   │
│   │  WHY: Losing a payment record means:                                │   │
│   │  - Customer charged but no record (we can't refund what we can't    │   │
│   │    find)                                                            │   │
│   │  - Regulatory violation (financial records must be retained)        │   │
│   │  - Reconciliation impossible (what went missing?)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CORRECTNESS:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Correctness > performance. Always.                                 │   │
│   │  - Every debit has a matching credit (double-entry)                 │   │
│   │  - Ledger balances daily (or immediately detects imbalance)         │   │
│   │  - No duplicate charges (idempotency enforced at every layer)       │   │
│   │  - State machine transitions are valid (no skipping states)         │   │
│   │                                                                     │   │
│   │  WHY: A payment system that processes 10,000 TPS but occasionally   │   │
│   │  double-charges is broken. A system that processes 100 TPS and      │   │
│   │  never double-charges is correct. Correct first, fast second.       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TRADE-OFFS ACCEPTED:                                                      │
│   - Higher authorization latency (processor-dependent, 2-5s acceptable)     │
│   - Lower refund availability (manual fallback exists)                      │
│   - Capture may be delayed minutes under load (queue + retry)               │
│                                                                             │
│   TRADE-OFFS NOT ACCEPTED:                                                  │
│   - Double charges (non-negotiable)                                         │
│   - Missing ledger entries (non-negotiable)                                 │
│   - Lost payment records (non-negotiable)                                   │
│   - Unauditable state transitions (non-negotiable)                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Scale & Capacity Planning

## Scale Estimates

```
ASSUMPTIONS:

    Orders per day: 100,000 (~1.2 orders/sec average)
    Peak: 10 orders/sec (flash sale, promotional events)
    Payment attempts per order: ~1.2 (some retries on decline)
    
    Payment operations per order:
        1 create + 1 authorize + 1 capture = 3 writes/order
        + 1 ledger entry (2 rows: debit + credit) = 2 writes
        Total: ~5 DB writes per successful payment
    
    Write QPS (average): 1.2 orders/sec × 5 = 6 writes/sec
    Write QPS (peak): 10 orders/sec × 5 = 50 writes/sec
    
    Read QPS:
        Status checks: ~5 QPS (user polling, support lookups)
        Reconciliation: 1 batch job/day (100K comparisons in ~10 min)
        Dashboard queries: ~1 QPS
        Total read QPS: ~7 QPS
    
    STORAGE:
    Payment record: ~1 KB (metadata + processor response + audit fields)
    Ledger entry: ~200 bytes per row (2 rows per payment = 400 bytes)
    Daily storage: 100K × 1.4 KB = ~140 MB/day
    Annual storage: ~50 GB/year
    
    Retention: Permanent (financial records; regulatory requirement)
    
    With indexes and audit logs: ~100 GB/year total

WRITE:READ RATIO: ~1:1 (balanced; both are light at this scale)

REALITY CHECK:
    50 writes/sec peak is trivial for PostgreSQL.
    Payment systems are NOT high-throughput systems like metrics or search.
    The complexity is in CORRECTNESS, not SCALE.
    
    Most payment systems serve < 1,000 TPS even at large scale.
    The hard problem is never "can the DB handle the load?"
    It's "can we guarantee no double-charges at any load?"
```

## What Breaks First

```
SCALE GROWTH:

| Scale  | Orders/day | Peak TPS | What Changes           | What Breaks First           |
|--------|-----------|----------|-------------------------|-----------------------------|
| 1×     | 100K      | 10       | Baseline                | Nothing                     |
| 5×     | 500K      | 50       | More API instances      | Processor rate limits       |
| 10×    | 1M        | 100      | Read replicas for status| Processor cost              |
| 50×    | 5M        | 500      | Shard by merchant/region| Reconciliation job duration |

MOST FRAGILE ASSUMPTION: Single payment processor.

    At 1× (100K/day): Stripe handles this easily (Stripe's limit is millions/day).
    At 10× (1M/day): Processor rate limits may apply (negotiate higher limits).
    Real risk: Processor outage. If Stripe is down, ALL payments fail.
    
    Mitigation (V1): Queue payments during brief outages; retry when back.
    Mitigation (V2): Multi-processor support (failover to Adyen if Stripe down).
    
SECOND FRAGILE ASSUMPTION: Reconciliation as a single daily job.
    At 5M orders/day: Reconciling 5M records takes hours, not minutes.
    Mitigation: Streaming reconciliation (compare as transactions settle,
    not in one nightly batch).
```

---

# Part 6: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PAYMENT FLOW ARCHITECTURE                                │
│                                                                             │
│                                                                             │
│  ┌──────────┐         ┌──────────┐         ┌──────────┐                     │
│  │ Frontend │         │  Order   │         │ Support  │                     │
│  │ (User)   │         │ Service  │         │  Tool    │                     │
│  └────┬─────┘         └────┬─────┘         └────┬─────┘                     │
│       │                    │                    │                           │
│       └────────────────────┼────────────────────┘                           │
│                            ▼                                                │
│              ┌──────────────────────────────┐                               │
│              │      PAYMENT API (×2)        │  ← Stateless, LB'd            │
│              │  Validate → Idempotency →    │                               │
│              │  State Machine → Persist     │                               │
│              └─────────────┬────────────────┘                               │
│                            │                                                │
│                            ▼                                                │
│              ┌──────────────────────────────┐                               │
│              │   POSTGRESQL (Primary)       │  ← Source of truth            │
│              │                              │                               │
│              │  ┌────────────────────────┐  │                               │
│              │  │ payments table         │  │  (state machine record)       │
│              │  │ ledger_entries table   │  │  (double-entry accounting)    │
│              │  │ refunds table          │  │  (refund lifecycle)           │
│              │  │ reconciliation_log     │  │  (daily reconciliation)       │
│              │  │ payment_events table   │  │  (audit trail)                │
│              │  └────────────────────────┘  │                               │
│              │                              │                               │
│              │  Synchronous replica ──→     │  (zero-lag standby)           │
│              └─────────────┬────────────────┘                               │
│                            │                                                │
│              ┌─────────────┼──────────────┐                                 │
│              │             │              │                                 │
│              ▼             ▼              ▼                                 │
│     ┌──────────────┐ ┌──────────┐ ┌──────────────┐                          │
│     │  Processor   │ │  Ledger  │ │  Webhook     │                          │
│     │  Gateway     │ │  Writer  │ │  Dispatcher  │                          │
│     │              │ │          │ │              │                          │
│     │ Auth/Capture │ │ Double-  │ │ Notify Order │                          │
│     │ Refund calls │ │ entry    │ │ Svc, Email   │                          │
│     │ to Stripe    │ │ writes   │ │              │                          │
│     └──────┬───────┘ └──────────┘ └──────────────┘                          │
│            │                                                                │
│            ▼                                                                │
│     ┌──────────────┐                                                        │
│     │   Stripe /   │                                                        │
│     │   Adyen      │  ← External payment processor                          │
│     │   (3rd party)│                                                        │
│     └──────────────┘                                                        │
│                                                                             │
│   RECONCILIATION (daily):                                                   │
│   ┌────────────────────────────┐    ┌───────────────────────┐               │
│   │ Reconciliation Worker      │───→│ Finance Dashboard     │               │
│   │ - Pull processor report    │    │ - Discrepancy alerts  │               │
│   │ - Compare with ledger      │    │ - Revenue reports     │               │
│   │ - Flag mismatches          │    └───────────────────────┘               │
│   └────────────────────────────┘                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

REQUEST FLOW (Authorize + Capture, numbered steps):

1. Client: POST /payments {order_id, amount, token, idempotency_key}
2. Payment API: Validate, idempotency check, create payment (status: "created")
3. Payment API → Processor Gateway → Stripe: Authorize $49.99
4. Stripe responds: authorized (auth_code: AUTH_789)
5. Payment API: Update payment (status: "authorized"), write payment_event
6. Payment API → Webhook: Notify Order Service ("authorized")
7. [Later] Order Service: POST /payments/{id}/capture
8. Payment API → Processor Gateway → Stripe: Capture AUTH_789
9. Stripe responds: captured (capture_id: CAP_456)
10. Payment API: Update payment (status: "captured"), write payment_event
11. Ledger Writer: INSERT debit + credit entries
12. Webhook Dispatcher: Notify Order Service ("captured"), queue receipt email
```

### Architecture Decisions

```
DECISIONS AND JUSTIFICATIONS:

1. PostgreSQL (not DynamoDB, not event store)
   WHY: Payments need ACID transactions. A single DB transaction must
   atomically update payment status + write ledger entry + write audit event.
   If any fails, all fail. PostgreSQL provides this out of the box.
   
   DynamoDB: No multi-table transactions (or limited). Event store: Adds
   complexity for event sourcing that isn't needed at V1 scale.

2. Synchronous replication (not async)
   WHY: Async replication risks data loss on primary failure. Losing a
   payment record is unacceptable. Synchronous replication ensures the
   standby has every committed transaction before the primary confirms.
   
   Trade-off: ~1-2ms additional write latency. Acceptable for payments.

3. Separate Processor Gateway component (not inline)
   WHY: Isolates processor-specific logic (request format, auth, retry,
   timeout handling) from payment business logic. If we switch from Stripe
   to Adyen, we change the gateway, not the payment service.
   
   Also: Single place for processor-level idempotency, timeout config,
   and circuit breaker.

4. Double-entry ledger (not single-entry)
   WHY: Double-entry bookkeeping is the foundation of financial accounting
   for 500 years. Every transaction has a debit and a credit. The sum of
   all debits must equal the sum of all credits. If they don't, there's a
   bug. This invariant is the strongest correctness check in the system.

5. Webhook dispatcher (async notifications, not sync callbacks)
   WHY: Payment capture should not fail because the Order Service is
   temporarily down. Capture the money (irreversible), then notify
   asynchronously with retries. Money movement and notification are
   decoupled.
```

---

# Part 7: Component-Level Design

## Payment API

```
COMPONENT: PAYMENT API

Purpose: Accept payment operations, enforce state machine, persist state

State machine:
    created → authorized → captured → (optionally) refunded
    created → declined (terminal)
    created → authorization_failed (terminal, retriable by user)
    authorized → voided (authorization released)
    authorized → capture_failed → (retry or escalate)
    captured → partially_refunded → fully_refunded

Valid transitions (enforced):
    CURRENT STATE              ALLOWED NEXT STATES
    created                   → authorized, declined, authorization_failed
    authorized                → captured, voided, capture_failed, authorization_expired
    capture_failed            → captured (retry), voided (give up)
    captured                  → partially_refunded, fully_refunded, disputed
    partially_refunded        → fully_refunded
    disputed                  → captured (dispute won), chargebacked (dispute lost)
    declined                  → (terminal, no transitions)
    authorization_failed      → (terminal, no transitions)
    authorization_expired     → (terminal, no transitions)
    voided                    → (terminal, no transitions)
    fully_refunded            → (terminal, no transitions)
    chargebacked              → (terminal, no transitions)

    ANY TRANSITION NOT IN THIS LIST IS REJECTED.
    Code: UPDATE payments SET status = $new WHERE id = $id AND status = $expected
    If 0 rows updated → Invalid transition → Return 409 Conflict

Concurrency control:
    Optimistic locking via status column.
    Two concurrent capture attempts:
    → First: UPDATE ... WHERE status = 'authorized' → 1 row → succeeds
    → Second: UPDATE ... WHERE status = 'authorized' → 0 rows → conflict
    No explicit locks needed. State machine + atomic update = safe.

Failure behavior:
    - DB write fails: Return 503; client retries with same idempotency_key
    - Processor call fails: Leave in current state; retry scheduled
    - API crash: Stateless; load balancer routes to other instance; DB state is safe
```

## Processor Gateway

```
COMPONENT: PROCESSOR GATEWAY

Purpose: Abstract payment processor API; handle retries, timeouts, idempotency

Key responsibilities:
    1. Format requests for specific processor (Stripe, Adyen)
    2. Send with processor-level idempotency key
    3. Handle timeout (5-second default)
    4. Retry with same idempotency key (max 3 attempts)
    5. Parse response into normalized format
    6. Circuit breaker if processor error rate > 50%

Timeout handling:
    authorize_timeout: 5 seconds
    capture_timeout: 10 seconds (captures can be slower)
    refund_timeout: 10 seconds
    
    On timeout:
    → DO NOT mark as failed immediately
    → Schedule status check: query processor for transaction by idempotency_key
    → If processor says "authorized": Update our record accordingly
    → If processor says "not found": Safe to retry
    → If status check also times out: Wait and retry status check
    
    CRITICAL: Never assume timeout means failure. Timeout means UNKNOWN.
    The conservative response to unknown is: CHECK, don't RETRY blindly.

Processor abstraction:
    interface PaymentProcessor:
        authorize(amount, currency, token, idempotency_key) → AuthResult
        capture(auth_code, amount, idempotency_key) → CaptureResult
        refund(capture_id, amount, idempotency_key) → RefundResult
        get_transaction(idempotency_key) → TransactionStatus

    StripeProcessor implements PaymentProcessor
    AdyenProcessor implements PaymentProcessor (V2)

    WHY abstract: Processor switch should require 0 changes to payment logic.
    Only the gateway implementation changes.

Circuit breaker:
    If processor error rate > 50% over 2 minutes:
    → Open circuit: Return "processor_unavailable" for new requests
    → Pending authorizations: Queue for retry when circuit closes
    → Check every 30 seconds: Send probe request. If success → close circuit.
    
    WHY: If Stripe is down, hammering it with retries is wasteful and
    may trigger their rate limits. Better to fail fast, queue, and recover.
```

## Ledger Writer

```
COMPONENT: LEDGER WRITER

Purpose: Record financial transactions as double-entry ledger entries

Ledger entry structure:
    LedgerEntry {
        entry_id: UUID
        payment_id: UUID       // Links to payment record
        account: string        // "customer_receivable", "revenue", "refund_payable"
        entry_type: DEBIT | CREDIT
        amount_cents: integer  // Always positive
        currency: string
        created_at: timestamp
    }

Double-entry rules:
    For every transaction, total DEBITS = total CREDITS.
    
    Capture $49.99:
        DEBIT  customer_receivable  4999
        CREDIT revenue              4999
    
    Refund $49.99:
        DEBIT  revenue              4999
        CREDIT refund_payable       4999

    Invariant check (daily):
        SELECT SUM(CASE WHEN entry_type = 'DEBIT' THEN amount_cents ELSE 0 END) as total_debits,
               SUM(CASE WHEN entry_type = 'CREDIT' THEN amount_cents ELSE 0 END) as total_credits
        FROM ledger_entries;
        
        IF total_debits ≠ total_credits: ALERT IMMEDIATELY.
        This should NEVER happen. If it does, there's a bug.

Atomicity:
    Payment status update + ledger entries written in the SAME DB transaction.
    
    BEGIN;
      UPDATE payments SET status = 'captured', captured_at = NOW()
        WHERE id = $payment_id AND status = 'authorized';
      INSERT INTO ledger_entries (payment_id, account, entry_type, amount_cents, currency)
        VALUES ($id, 'customer_receivable', 'DEBIT', 4999, 'USD');
      INSERT INTO ledger_entries (payment_id, account, entry_type, amount_cents, currency)
        VALUES ($id, 'revenue', 'CREDIT', 4999, 'USD');
      INSERT INTO payment_events (payment_id, event_type, details)
        VALUES ($id, 'captured', '{"capture_id": "CAP_456"}');
    COMMIT;
    
    If any INSERT fails, the entire transaction rolls back.
    Payment stays "authorized." Retry safe.

Immutability:
    Ledger entries are NEVER updated or deleted.
    Corrections are done via new entries (reversal + correction).
    WHY: Audit trail. Regulators need to see the original entry AND the correction.
```

---

# Part 8: Data Model & Storage

## Schema

```sql
-- Core payment record (state machine)
CREATE TABLE payments (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id              UUID NOT NULL,
    amount_cents          INTEGER NOT NULL CHECK (amount_cents > 0),
    currency              VARCHAR(3) NOT NULL DEFAULT 'USD',
    status                VARCHAR(32) NOT NULL DEFAULT 'created',
    payment_method_token  VARCHAR(256) NOT NULL,
    
    -- Processor references
    processor             VARCHAR(64) NOT NULL DEFAULT 'stripe',
    processor_auth_code   VARCHAR(256),
    processor_capture_id  VARCHAR(256),
    processor_decline_reason VARCHAR(512),
    
    -- Idempotency
    idempotency_key       VARCHAR(256) NOT NULL,
    
    -- Timestamps
    created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    authorized_at         TIMESTAMP,
    captured_at           TIMESTAMP,
    
    -- Refund tracking
    total_refunded_cents  INTEGER NOT NULL DEFAULT 0,
    
    CONSTRAINT valid_status CHECK (status IN (
        'created', 'authorized', 'declined', 'authorization_failed',
        'authorization_expired', 'captured', 'capture_failed', 'voided',
        'disputed', 'chargebacked',
        'partially_refunded', 'fully_refunded'
    )),
    CONSTRAINT valid_refund CHECK (total_refunded_cents <= amount_cents)
);

-- Idempotency enforcement
CREATE UNIQUE INDEX idx_payments_idempotency ON payments (idempotency_key);

-- Order lookup
CREATE INDEX idx_payments_order ON payments (order_id);

-- Status queries (support, monitoring)
CREATE INDEX idx_payments_status ON payments (status, created_at);


-- Double-entry ledger (append-only, immutable)
CREATE TABLE ledger_entries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id    UUID NOT NULL REFERENCES payments(id),
    account       VARCHAR(64) NOT NULL,
    entry_type    VARCHAR(6) NOT NULL CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),
    currency      VARCHAR(3) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ledger_payment ON ledger_entries (payment_id);
CREATE INDEX idx_ledger_account ON ledger_entries (account, created_at);


-- Refund records
CREATE TABLE refunds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id      UUID NOT NULL REFERENCES payments(id),
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    currency        VARCHAR(3) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'created',
    reason          TEXT NOT NULL,
    initiated_by    VARCHAR(128) NOT NULL,
    
    processor_refund_id VARCHAR(256),
    idempotency_key     VARCHAR(256) NOT NULL,
    
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    
    CONSTRAINT valid_refund_status CHECK (status IN (
        'created', 'processing', 'refunded', 'refund_failed'
    ))
);

CREATE UNIQUE INDEX idx_refunds_idempotency ON refunds (idempotency_key);
CREATE INDEX idx_refunds_payment ON refunds (payment_id);


-- Audit trail (every state transition)
CREATE TABLE payment_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id    UUID NOT NULL REFERENCES payments(id),
    event_type    VARCHAR(64) NOT NULL,
    details       JSONB,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_payment ON payment_events (payment_id, created_at);


-- Reconciliation results
CREATE TABLE reconciliation_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reconciliation_date     DATE NOT NULL,
    processor               VARCHAR(64) NOT NULL,
    total_processor_amount  BIGINT NOT NULL,
    total_ledger_amount     BIGINT NOT NULL,
    discrepancy_count       INTEGER NOT NULL DEFAULT 0,
    discrepancy_details     JSONB,
    status                  VARCHAR(16) NOT NULL DEFAULT 'clean',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);
```

## Key Design Decisions

```
SCHEMA DECISIONS:

1. amount_cents as INTEGER (not DECIMAL or FLOAT)
   WHY: Floating point introduces rounding errors ($49.99 becomes $49.989999...).
   Integer cents eliminates rounding entirely. $49.99 = 4999 cents. Always.
   
   This is industry standard for money handling. Any engineer who stores
   money as FLOAT will eventually have a reconciliation discrepancy.

2. Separate ledger_entries table (not embedded in payments)
   WHY: Ledger is append-only, immutable, and may have more entries than
   payments (refunds, corrections, adjustments). Ledger must be independently
   queryable: "What's the total revenue for January?" is a ledger query,
   not a payment query.

3. payment_events table (full audit trail)
   WHY: Regulators require a complete history of what happened to every
   payment. "Show me every action taken on payment X" = SELECT * FROM
   payment_events WHERE payment_id = X ORDER BY created_at.
   
   Also: Debugging. "Why is this payment stuck in 'authorized'?" Check
   events: last event was "authorization_succeeded" at 14:30; no capture
   event → capture was never triggered → Order Service didn't call capture.

4. idempotency_key on payments AND refunds
   WHY: Both operations can be retried by clients. Both must be safe to
   retry. Same key = same result.

5. Permanent retention (no TTL, no deletion)
   WHY: Financial records have legal retention requirements (7+ years
   in most jurisdictions). Never delete. Archive to cold storage after
   2 years if active DB storage is a concern.
```

---

# Part 9: Consistency, Concurrency & Idempotency

## Consistency Guarantees

```
CONSISTENCY MODEL: Strong consistency for payment state, eventual for notifications

PAYMENT STATE: Linearizable.
    A payment has exactly one status at any time. Transitions are atomic.
    After UPDATE commits, all readers see the new status.
    
    WHY: "Is this payment authorized?" must have a single, definitive answer.
    Two different services seeing "authorized" and "captured" simultaneously
    could lead to double-capture or missed capture.

NOTIFICATIONS: Eventually consistent.
    After capture, the Order Service learns about it via webhook.
    Delay: Typically < 5 seconds, up to 5 minutes under failure.
    
    WHY: Webhook delivery should not block money movement.
    Capture the money first. Notify second. Retry notification if it fails.

LEDGER: Atomically consistent with payment state.
    Ledger entries are written in the same transaction as payment status update.
    If payment says "captured," ledger has the debit/credit. Always.
```

## Idempotency (Two Layers)

```
IDEMPOTENCY LAYER 1: CLIENT → PAYMENT SERVICE

    Client provides idempotency_key with every request.
    
    Create payment:
        INSERT INTO payments (..., idempotency_key) VALUES (..., $key)
        ON CONFLICT (idempotency_key) DO NOTHING
        
        If conflict: SELECT * FROM payments WHERE idempotency_key = $key
        Return existing payment (same payment_id, current status).
    
    Capture/refund:
        Idempotency enforced by state machine.
        Capture on "authorized" → succeeds. Capture on "captured" → return success (no-op).
        No need for separate idempotency key; state is the guard.

IDEMPOTENCY LAYER 2: PAYMENT SERVICE → PROCESSOR

    Every processor call includes a processor-level idempotency key.
    
    authorize: idempotency_key = "order-1234-auth"
    capture: idempotency_key = "order-1234-capture"
    refund: idempotency_key = "order-1234-refund-{refund_id}"
    
    If we retry (after timeout), the processor sees the same key and returns
    the cached result. No duplicate charge.
    
    CRITICAL: These keys MUST be deterministic (derived from order/payment/refund ID).
    Never use random UUIDs as processor idempotency keys—a retry would generate
    a new UUID, defeating the purpose.
```

## Race Conditions

```
RACE CONDITION 1: Double-capture (two capture requests simultaneously)

    Request A: POST /payments/123/capture
    Request B: POST /payments/123/capture (duplicate click or retry)
    
    Prevention: State machine + atomic update.
    
    Request A: UPDATE payments SET status = 'captured'
               WHERE id = 123 AND status = 'authorized'
    → 1 row updated. Success. Proceed to processor capture.
    
    Request B: UPDATE payments SET status = 'captured'
               WHERE id = 123 AND status = 'authorized'
    → 0 rows updated (status is now 'captured', not 'authorized').
    → Return 200 with current status: "already captured."
    
    No double-capture. No race.

RACE CONDITION 2: Capture and void simultaneously

    Thread A: Capture (order shipped)
    Thread B: Void (order cancelled)
    
    Prevention: Same mechanism. First UPDATE wins.
    
    Thread A: UPDATE ... WHERE status = 'authorized' → 1 row → captures
    Thread B: UPDATE ... WHERE status = 'authorized' → 0 rows → conflict
    
    Result: Payment is captured. Void fails. Support must refund instead.
    
    WHY this order is correct: Once money moves (capture), you can't un-capture.
    You can only refund. The state machine enforces this: captured → voided
    is not a valid transition. Only authorized → voided is valid.

RACE CONDITION 3: Timeout retry creates duplicate at processor

    T=0: Send authorize to Stripe with idempotency_key "order-1234-auth"
    T=5: Timeout. No response.
    T=6: Retry authorize to Stripe with SAME key "order-1234-auth"
    T=7: Stripe processes first request → auth_code AUTH_001
    T=8: Stripe receives retry → sees same key → returns cached AUTH_001
    
    No duplicate. Processor idempotency key prevents double-charge.

RACE CONDITION 4: Concurrent refund requests

    Support Agent A: Refund $30 on payment 123
    Support Agent B: Refund $30 on payment 123 (same request, both clicked)
    
    Prevention: Idempotency key on refund + total_refunded_cents check.
    
    Agent A's request: idempotency_key = "order-1234-refund-manual-1"
    Agent B's request: Same key → returns existing refund (no duplicate)
    
    If DIFFERENT keys (different refund reasons):
    Agent A: Refund $30 → total_refunded = 30 (of 4999) → succeeds
    Agent B: Refund $30 → total_refunded = 60 (of 4999) → succeeds
    Both are legitimate partial refunds? Or duplicate mistake?
    
    SAFEGUARD: Total refund cannot exceed captured amount.
    CHECK (total_refunded_cents <= amount_cents) enforced in DB.
    If Agent B tries to refund $4999 after Agent A's $30:
    → 30 + 4999 > 4999 → rejected (over-refund).
```

## Clock Assumptions

```
CLOCK HANDLING:

    All timestamps: Database server clock (NOW() in PostgreSQL).
    NOT application server clock.
    
    WHY: Multiple API instances. Clock skew between servers could cause:
    - authorized_at > captured_at (nonsensical timeline)
    - Reconciliation mismatches (our timestamp vs processor timestamp)
    
    Processor timestamps: Stored as received (processor's clock).
    Internal timestamps: DB clock.
    Reconciliation: Compare by processor transaction ID, not by timestamp.
```

---

# Part 10: Failure Handling & Reliability (Ownership-Focused)

## Failure Mode Table

| Failure Type | Handling Strategy |
|--------------|-------------------|
| **Processor timeout** | Queue status check; retry with same idempotency key; never assume failure |
| **Processor down** | Circuit breaker; queue pending operations; fail gracefully to user |
| **DB write failure** | Return 503; client retries with idempotency key; no partial state |
| **Double-charge detected** | Alert immediately; auto-void second authorization; escalate |
| **Ledger imbalance** | Critical alert; halt captures; investigate before resuming |
| **Reconciliation discrepancy** | Flag, alert finance team; investigate within 24 hours |

## Blast Radius & Containment (Staff-Level)

```
STAFF QUESTION: "When this fails, how far does it propagate?"

BLAST RADIUS BY FAILURE TYPE:

| Failure                         | Blast radius              | Containment strategy                        |
|---------------------------------|---------------------------|--------------------------------------------|
| Ledger bug (missing entry)      | All payments after deploy | Halt new captures; deploy fix; backfill    |
| Idempotency bug (double-charge) | All orders during window  | Halt auth; void duplicates; fix key gen    |
| Processor outage               | All new payments          | Circuit breaker; queue; fail gracefully   |
| DB failover                    | 10–30s of in-flight txns  | Recovery job: reconcile Stripe vs ledger   |
| Reconciliation job crash       | Delayed detection         | Hourly partial runs; alert on no report   |

STAFF INSIGHT: Payment failures propagate to Order Service (unfulfilled orders),
Finance (wrong revenue numbers), Support (ticket volume), and customers (trust).
Containment means: (1) Stop the bleeding (halt new captures if ledger wrong),
(2) Isolate scope (which payments affected?), (3) Correct before resuming.
```

## Cross-Team Ownership & Handoffs (Staff-Level)

```
STAFF QUESTION: "Who owns what when it breaks?"

| Scenario                          | Primary owner   | Secondary / handoff        |
|-----------------------------------|-----------------|----------------------------|
| Ledger imbalance                  | Payment team    | Finance validates correction|
| Reconciliation discrepancy        | Payment team    | Finance approves adjustments|
| Processor outage                  | Payment team    | Order Service: hold orders  |
| Chargeback received               | Payment team   | Support: evidence submission|
| Refund fraud / abuse              | Support + Payment | Security if systematic  |
| Compliance audit                  | Payment + Legal | Finance for records        |

HANDOFF PROTOCOL: When Payment team detects a discrepancy requiring Finance
approval (e.g., manual ledger correction), create ticket with:
- Affected payment IDs, amount, root cause
- Proposed correction (new ledger entry)
- Finance sign-off before applying

STAFF INSIGHT: Payment correctness is not owned by one team. Finance owns
revenue numbers; Support owns customer experience; Payment owns the flow.
Document these boundaries so 2 AM incidents don't devolve into "who fixes this?"
```

## Detailed Failure Strategies

```
RETRY POLICY (Processor Calls):

    Authorization: Max 3 retries, 2s/4s/8s backoff + jitter
    Capture: Max 5 retries, 10s/30s/60s/120s/300s backoff + jitter
    Refund: Max 5 retries, same schedule as capture
    
    WHY more retries for capture:
    Authorization: Customer is waiting. Fail fast, tell them to try again.
    Capture: Customer already received value. We MUST capture. Retry harder.
    
    WHY backoff + jitter:
    If processor is recovering from overload, thundering herd of retries
    makes it worse. Jitter distributes load.

TIMEOUT POLICY:

    Processor calls: 5 seconds (authorization), 10 seconds (capture/refund)
    
    On timeout:
    1. DO NOT retry immediately
    2. Query processor: GET /transactions?idempotency_key=X
    3. If processor says authorized/captured: Update our record
    4. If processor says not found: Safe to retry original request
    5. If status query also times out: Wait 30s, try status query again
    
    PRINCIPLE: Check before retry. Retrying without checking risks
    hitting a processor that processed the FIRST request but is slow
    responding. The retry creates a NEW transaction (if idempotency
    key not supported for that operation).

CONSERVATIVE DEFAULTS:

    When in doubt about authorization: Treat as failed.
    → Customer is NOT charged. They can retry.
    → Better: $49.99 missed sale. Worse: $99.98 double-charge.
    
    When in doubt about capture: Treat as pending, retry.
    → Customer IS already authorized. We should capture.
    → If capture fails permanently: Void the authorization.
    
    When in doubt about refund: Treat as pending, retry.
    → Customer expects money back. We should complete the refund.
    → If refund fails permanently: Alert finance for manual processing.
```

## Structured Real Incident (Staff-Level)

At least one production incident should be documented in this format for Staff-level learning. Below is the double-charge incident in structured form.

| Part | Content |
|------|---------|
| **Context** | Payment flow processing 100K orders/day. Single processor. Authorization timeout: 5 seconds. Processor latency spike during morning peak. |
| **Trigger** | Processor latency P99 rises from 2s to 8s. First authorization request sent at T=0; processor completes at T=3; response lost at T=5 (timeout). Retry sent at T=7 with different idempotency key (bug: key included `datetime.now()`). |
| **Propagation** | 340 customers double-authorized during 20-minute spike. Each has two holds on card (AUTH_001 and AUTH_002). Second request processed as new authorization. No circuit breaker on retry path. |
| **User impact** | Customers see $99.98 pending instead of $49.99. Support flooded with "charged twice" tickets. $17K in double-holds (not yet captured). |
| **Engineer response** | Void all second authorizations via script. Customer communication: "Temporary hold will be released in 3–5 days." Fix: Idempotency key = "order-{order_id}-auth" (deterministic). Deploy within 4 hours. |
| **Root cause** | Non-deterministic idempotency key generation. Retry produced different key; processor treated it as new transaction. |
| **Design change** | Idempotency keys derived from business identifiers only. Code review checklist for idempotency. Hourly reconciliation check: "Any order with 2+ auth codes?" Alert: "Duplicate processor refs for same order." |
| **Lesson** | *"Idempotency keys must be deterministic—derived from order/payment ID, never from timestamps or random values. A retry with a different key is a new charge."* |

---

## Production Failure Scenario: Ambiguous Timeout Causes Double-Charge (Detailed)

```
SCENARIO: Stripe authorization API returns 504 after 5 seconds. The
authorization actually succeeded at Stripe but the response was lost.
Our system retries with a DIFFERENT idempotency key (BUG in key generation).
Result: Two authorizations on the customer's card.

1. TRIGGER:
   - Stripe latency spike (P99 goes from 2s to 8s)
   - Our timeout: 5 seconds
   - First request: Sent at T=0, Stripe processes at T=3, response lost at T=5 (timeout)
   - Retry: Sent at T=7 with DIFFERENT idempotency key (bug: key includes timestamp)
   - Stripe processes retry as NEW authorization
   - Two holds on customer's card: AUTH_001 and AUTH_002

2. IMPACT:
   - 340 customers double-authorized during the 20-minute latency spike
   - Each has two holds on their card (shows as $99.98 pending, not $49.99)
   - Customer support flooded: "Why was I charged twice?"
   - Revenue impact: $17K in double-holds (not captured, but customer sees it)

3. DETECTION:
   - Alert: "Authorization success rate > 100%" (more auths than attempts)
     Wait—that's not a real metric. REAL detection:
   - Customer complaints: 12 tickets in 30 minutes ("charged twice")
   - Reconciliation (next day): 340 transactions with duplicate processor refs
   - Proactive: Alert on "duplicate auth_code for same order_id"

4. TRIAGE:
   - Check: Do any orders have 2+ payments? Yes, 340.
   - Check: Is the idempotency key generation deterministic? No—BUG: key
     includes `datetime.now()`, which differs between original and retry.
   - Root cause: Non-deterministic idempotency key.

5. MITIGATION (immediate):
   - Void all second authorizations (AUTH_002 for each)
     Script: For each duplicate, void the newer auth_code
   - Customer communication: "A temporary hold will be released within 3-5 days"
   - Verify: No double-captures occurred (capture uses payment_id, not new auth)

6. RESOLUTION:
   - Fix: Idempotency key = "order-{order_id}-auth" (deterministic, no timestamp)
   - Deploy fix immediately
   - Verify: Retry now returns same auth_code (no duplicate)

7. POST-MORTEM:
   - Action item: Idempotency keys must be derived from business identifiers,
     NEVER include timestamps, random values, or retry counters
   - Action item: Add reconciliation check: "Any order with 2+ auth_codes?"
     Run hourly, not just daily
   - Action item: Add alert: "Duplicate processor references for same order"
   - Process change: Code review checklist includes idempotency key validation
```

## Orphaned Authorization Detection & Cleanup

```
PROBLEM: Authorizations expire (7 days for most processors). If a payment
is authorized but never captured (Order Service didn't trigger capture),
the authorization hold expires and the customer's funds are released.
But our system still shows "authorized"—a stale state.

WHY THIS MATTERS:
    - Customer sees "pending charge" on their card statement for 7 days
    - If we try to capture after expiry: Processor rejects ("auth expired")
    - Order is unfulfilled: Either re-authorize or cancel
    - Accumulated orphaned authorizations = customer complaints + support load

DETECTION:

    Scheduled job (hourly):
    SELECT id, order_id, amount_cents, authorized_at
    FROM payments
    WHERE status = 'authorized'
      AND authorized_at < NOW() - INTERVAL '6 days'
    ORDER BY authorized_at;

    WHY 6 days (not 7): Buffer. Attempt capture or void BEFORE expiry.
    
HANDLING:

    For each orphaned authorization:
    1. Check with Order Service: Is this order still valid?
       a. Order valid + ready to ship → Capture immediately (before auth expires)
       b. Order cancelled → Void authorization (release hold on customer's card)
       c. Order still pending → Alert: "Order #X authorized 6 days ago, not captured"
    
    2. If authorization already expired (> 7 days):
       → Status → "authorization_expired" (new terminal state)
       → Order Service decides: Re-authorize with new customer consent, or cancel order
       → Customer notification: "Your payment authorization expired. Please re-submit."
    
    3. Void explicitly when possible:
       → Don't let authorizations expire passively
       → Explicit void releases the hold immediately (not 7 days)
       → Better customer experience

STATE MACHINE ADDITION:
    authorized → authorization_expired (timer-based, 7 days)
    authorized → voided (explicit release)

METRIC:
    "Authorization void rate" (already in operational alerts)
    If > 5%: Orders aren't being fulfilled → investigate Order Service

TRADE-OFF:
    Running this hourly adds ~1 query/hour (trivial).
    Not running it: Customer support tickets about "pending charges" that
    were never captured but show on their statement for a week.
```

## Processor Inbound Webhooks (Chargebacks & Async Events)

```
PROBLEM: The chapter covers OUR outbound webhooks (notifying Order Service).
But processors ALSO push events TO US: chargebacks, disputes, authorization
expiry notifications, settlement confirmations. Ignoring inbound webhooks
means missing critical processor-initiated state changes.

INBOUND WEBHOOK EVENTS:

1. CHARGEBACK / DISPUTE
   Stripe sends: {type: "charge.dispute.created", payment_intent: "pi_123",
                   amount: 4999, reason: "fraudulent"}
   
   HANDLING:
   a. Find payment by processor reference
   b. Update status: "captured" → "disputed"
   c. Write payment_event: {type: "dispute_created", details: {reason, amount}}
   d. Write reverse ledger entry: DEBIT revenue, CREDIT dispute_reserve
      (Money is held by processor pending dispute resolution)
   e. Alert: "Dispute received for payment $payment_id, order $order_id"
   f. Notify support team for evidence submission (evidence deadline: 7-21 days)
   
   STATE MACHINE ADDITION:
   captured → disputed (processor-initiated)
   disputed → captured (dispute won: money returned)
   disputed → chargebacked (dispute lost: money gone)

2. DISPUTE RESOLUTION
   Stripe sends: {type: "charge.dispute.closed", status: "won" | "lost"}
   
   won:
   → Status: "disputed" → "captured" (restored)
   → Reverse the dispute ledger entry
   → DEBIT dispute_reserve, CREDIT revenue (money returned)
   
   lost:
   → Status: "disputed" → "chargebacked" (terminal)
   → Ledger: dispute_reserve becomes permanent loss
   → DEBIT dispute_reserve, CREDIT chargeback_loss
   → Alert finance: Revenue permanently lost for this payment

3. AUTHORIZATION EXPIRY (processor notification)
   Some processors notify when an auth hold expires.
   → Status: "authorized" → "authorization_expired"
   → Complements our internal orphaned auth detection job

WEBHOOK ENDPOINT DESIGN:

    POST /webhooks/stripe
    
    Steps:
    1. Verify webhook signature (Stripe signs all webhooks with shared secret)
       → Reject if signature invalid (prevents spoofing)
    2. Parse event type
    3. Find matching payment by processor reference
    4. Apply state transition (state machine enforces validity)
    5. Return 200 OK to Stripe
    6. If processing fails: Return 500; Stripe retries (up to 3 days)
    
    IDEMPOTENCY:
    Stripe may deliver the same webhook multiple times.
    Store webhook event_id in payment_events.
    If event_id already processed → return 200 (no-op).
    
    ORDERING:
    Webhooks may arrive out of order.
    State machine prevents invalid transitions:
    If "dispute.closed" arrives before "dispute.created":
    → No payment in "disputed" state → transition rejected → return 200
    → When "dispute.created" arrives later → processes correctly
    → Then re-process "dispute.closed" on next Stripe retry

SECURITY:
    - Webhook endpoint authenticated via Stripe signature verification
    - NOT behind general API auth (Stripe can't provide our JWT)
    - IP allowlist as additional layer (optional, Stripe publishes IP ranges)
    - Rate limit: 100 req/sec (Stripe sends < 10/sec normally)

WHY THIS MATTERS FOR L5:
    A Senior engineer doesn't just build the outbound payment flow.
    They know that the processor pushes events back, and those events
    can change payment state (disputes move money). Ignoring inbound
    webhooks means chargebacks go unrecorded, the ledger drifts from
    reality, and reconciliation catches it days late instead of immediately.
```

---

# Part 11: Performance & Optimization

## Hot Paths

```
HOT PATH 1: CREATE PAYMENT (user-facing, must be fast)

    Client → Payment API → INSERT into PostgreSQL → Return payment_id
    
    Target: < 50ms P99
    
    Optimizations applied:
    - Connection pooling
    - Prepared statements
    - Idempotency check via unique index (single query, not read-then-write)
    
    Optimizations NOT applied:
    - Async write (risk: crash before persist = lost payment intent)
    - Cache (payment records change rapidly; caching adds staleness risk)

HOT PATH 2: AUTHORIZATION (user is waiting for "payment confirmed")

    Payment API → Processor → Response → Update DB
    
    Target: < 5 seconds P99 (dominated by processor latency)
    
    Our overhead target: < 100ms (DB read + DB write + business logic)
    
    Optimizations applied:
    - Single DB transaction for status update + event write
    - Processor connection pooling (reuse HTTP connections to Stripe)
    - Timeout at 5 seconds (fail fast, don't keep user waiting 30s)
    
    Optimizations NOT applied:
    - Parallel auth + capture (must be sequential; authorize before capture)
    - Pre-authorization (authorize before user clicks; risky, complex)
```

## Caching

```
CACHING STRATEGY:

    Payment records: NO CACHE.
    
    WHY: Payment state changes rapidly (created → authorized → captured
    in seconds). A cached "authorized" status when the payment is already
    "captured" could cause a second capture attempt. For money, stale
    data is dangerous data.
    
    Ledger entries: NO CACHE.
    
    WHY: Append-only. Read patterns are analytical (sum over time range),
    not point lookups. Caching individual entries doesn't help.
    
    Reconciliation reports: CACHE (generated once/day, read many times).
    
    WHY: Report is static after generation. Finance team views it
    throughout the day. Cache the report, not the raw data.

    A mid-level engineer might cache payment status for the status API.
    A Senior engineer recognizes that the risk of stale financial data
    outweighs the marginal latency improvement at 7 read QPS.
```

## What NOT to Optimize

```
OPTIMIZATIONS INTENTIONALLY NOT DONE:

1. BATCHING PROCESSOR CALLS
   WHY NOT: Each payment is independent. Batching delays individual
   payments (user waits for batch window). Processor APIs are designed
   for individual calls. Batching adds complexity for no benefit.

2. ASYNC AUTHORIZATION
   WHY NOT: User is waiting for "payment confirmed." Making it async
   means the user leaves the checkout page not knowing if they paid.
   Terrible UX. Auth must be synchronous from the user's perspective.

3. IN-MEMORY LEDGER WITH ASYNC PERSISTENCE
   WHY NOT: If the server crashes between in-memory write and disk
   persist, the ledger entry is lost. Lost ledger entry = imbalanced
   books = financial discrepancy. Unacceptable.

4. READ REPLICA FOR PAYMENT STATUS
   WHY NOT: At 7 read QPS, the primary handles it trivially. A read
   replica introduces replication lag risk: user checks status, sees
   "authorized" from stale replica while primary already has "captured."
   For money, this is confusing and potentially dangerous (triggers
   another capture attempt).
```

---

# Part 12: Cost & Operational Considerations

## Cost Breakdown

```
COST ESTIMATE (V1: 100K orders/day, AWS us-east-1):

    Payment API (2 instances, stateless):
        2 × t3.medium ($30/mo) = $60/month
    
    PostgreSQL (primary + synchronous standby):
        db.r5.large ($175/mo × 2) = $350/month
        Storage (100 GB × $0.115/GB) = $12/month
    
    Processor fees (dominant cost):
        Stripe: 2.9% + $0.30 per transaction
        Average order: $50
        Per transaction: $1.75
        100K orders/day × 30 days = 3M transactions
        Processor cost: 3M × $1.75 = $5,250,000/month
    
    Infrastructure: ~$500/month
    Processor: ~$5,250,000/month
    
    REALITY: Payment infrastructure cost is NOISE compared to processor fees.
    The database, API servers, and monitoring combined are < 0.01% of
    processor cost. Optimizing infrastructure cost is irrelevant.
    
    WHAT MATTERS: Processor fee negotiation. Moving from 2.9% to 2.5%
    on $150M GMV/year = $600K/year saved. That's where the real money is.
```

## Cost vs Operability

```
COST TRADE-OFFS:

| Decision                     | Cost Impact  | Operability Impact       | On-Call Impact                    |
|------------------------------|--------------|--------------------------|-----------------------------------|
| Synchronous replication      | +$175/mo     | Zero data loss           | Never explain lost payment record |
| Separate audit events table  | +$5/mo       | Full debugging history   | 5-minute incident triage          |
| Daily reconciliation job     | +$20/mo      | Catch discrepancies < 24h| Finance doesn't surprise you      |
| Multi-processor (V2)         | +$200/mo     | Processor failover       | Pager goes off less often         |

BIGGEST COST DRIVER: Processor fees ($5.25M/month).
SECOND: Chargebacks ($10-25 per dispute, plus revenue loss).
THIRD: Everything else ($500/month).

SENIOR ENGINEER'S FOCUS:
    - Reduce chargebacks (idempotency, clear receipts, fraud prevention)
    - Negotiate processor rates (volume discounts, competitive quotes)
    - Don't waste time optimizing $500/month infrastructure

STAFF ADDITION — COST OF FAILURE (beyond infra):

| Failure type          | Cost range              | Example                              |
|-----------------------|-------------------------|--------------------------------------|
| Double-charge (trust) | Customer churn, chargebacks | 340 customers × $15 chargeback + lost LTV |
| Ledger imbalance      | Regulatory penalty, audit failure | Books don't balance = audit fail |
| Compliance breach     | Fines, merchant account loss | PCI scope creep = $50K–500K/year |
| Reconciliation lag    | Discrepancy undetected  | $5K missed for 24h before detection  |

STAFF INSIGHT: Cost of trust loss > cost of revenue loss. One double-charge
incident can drive 10× more support load and permanent customer churn than
a 1-hour outage. Design for trust first.
```

## Operational Considerations

```
OPERATIONAL BURDEN:

    Daily:
    - Review reconciliation report (should be "clean" every day)
    - Check DLQ for failed processor calls
    - Verify ledger balance invariant (debits = credits)
    
    Weekly:
    - Review chargeback rate (should be < 0.5%)
    - Verify authorization void rate (authorizations not captured within 7 days)
    - Check processor API error rate trends
    
    On-call alerts:
    - "Ledger imbalance detected" → CRITICAL: Stop captures, investigate
    - "Reconciliation discrepancy > $1" → HIGH: Investigate within 4 hours
    - "Processor error rate > 20%" → HIGH: Check circuit breaker, check Stripe status
    - "Double-charge detected" → CRITICAL: Void second auth immediately
    - "Authorization void rate > 5%" → MEDIUM: Orders not being fulfilled?
```

## Misleading Signals & Debugging Reality

```
THE FALSE CONFIDENCE PROBLEM:

| Metric               | Looks Healthy        | Actually Broken                           |
|----------------------|----------------------|-------------------------------------------|
| Auth success rate    | 98%                  | 2% are silent timeouts treated as decline;|
|                      |                      | real rate unknown (money in limbo)        |
| Capture rate         | 100%                 | Captures succeed but ledger write fails   |
|                      |                      | (capture_ledger_pending; books wrong)     |
| Refund count         | 0 today              | Refund handler crashed; queue building up |
| Revenue (ledger)     | $4.9M today          | Missing $50K in captures that timed out   |
|                      |                      | and weren't retried                       |
| Error rate           | 0.1%                 | Idempotency absorbing duplicate charges;  |
|                      |                      | without it, 2% would be double-charges    |

REAL SIGNALS:
- "Payments stuck in 'created' for > 5 minutes" (auth never attempted or timed out)
- "Authorization success + no capture within 24 hours" (order flow broken)
- "Ledger balance ≠ 0 (debits ≠ credits)" (THE most critical signal in the system)
- "Processor settlements - ledger total > $1" (money discrepancy)
- "Duplicate processor references per order" (double-charge detector)

SENIOR APPROACH:
- Dashboard must show processor-sourced and ledger-sourced revenue side by side.
  If they diverge: Problem.
- "Payments in terminal-fail state" view: Shows all payments that will NEVER
  complete without manual intervention.
- Don't trust your own metrics alone. Reconcile against the processor daily.
  The processor is the other source of truth for what actually happened with money.

STAFF ADDITION — TIME-TO-DETECT & TIME-TO-FIX:

| Bug type             | Time to detect              | Time to fix (typical)     |
|----------------------|-----------------------------|----------------------------|
| Ledger imbalance     | 30 min (balance check)      | 1–4 hours (investigate + correct) |
| Double-charge        | Customer complaints or hourly recon | 2–4 hours (void + fix)    |
| Missed capture       | Daily reconciliation        | Same day (retry or void)   |
| Idempotency bug      | Duplicate-ref alert or recon| 4–8 hours (void + deploy)  |

STAFF INSIGHT: Detection latency is a design choice. Daily reconciliation =
up to 24h to detect. Hourly = up to 1h. Ledger balance check every 30 min =
faster catch for deploy-time bugs. Trade-off: More frequent checks = more
load and alert fatigue. Staff selects based on risk tolerance.
```

---

# Part 13: Security Basics & Abuse Prevention

## Authentication & Authorization

```
AUTHENTICATION:

    External (checkout):
    - User authenticated via session/JWT from auth service
    - Payment method token: Already tokenized by processor (Stripe.js)
    - Payment API NEVER receives raw card numbers (stays out of PCI scope)
    
    Internal (service-to-service):
    - Order Service → Payment API: mTLS or API key
    - Payment API → Processor: API secret key (stored in secrets manager)
    
    Admin (support/refund):
    - Support agents: OAuth/SSO with "payment_support" role
    - Refund operations: Require "payment_refund" permission
    - All admin actions logged in payment_events (audit trail)

AUTHORIZATION:

    Customer: Can initiate payment for their own orders only
    Order Service: Can capture/void payments it created
    Support: Can view any payment, initiate refunds
    Finance: Read-only access to ledger and reconciliation
    
    Principle of least privilege: No service can do more than it needs.
    Payment creation requires order ownership. Refund requires support role.
```

## Abuse Vectors

```
ABUSE VECTORS AND PREVENTION:

1. CARD TESTING (Fraudsters testing stolen cards)
   Attack: Enumerate card numbers by trying small charges ($1)
   Prevention:
   - Fraud detection service (pre-payment check, out of our scope)
   - Rate limit: Max 5 payment attempts per user per hour
   - Alert: High decline rate from single user/IP

2. REFUND FRAUD
   Attack: Customer claims refund for received goods
   Prevention:
   - Refund requires support agent (not self-service for V1)
   - Audit trail: Who initiated, when, why
   - Refund amount validation: Cannot exceed captured amount
   - Alert: Refund rate > 5% (unusual chargeback pattern)

3. REPLAY ATTACK (Resubmitting captured request)
   Attack: Replay a valid payment creation request
   Prevention:
   - Idempotency key: Replay returns existing payment (no duplicate)
   - Payment linked to order: Same order can't have two active payments

4. INTERNAL FRAUD (Employee creating fake refunds)
   Prevention:
   - Refund audit trail (who, when, amount, reason)
   - Daily reconciliation catches unauthorized refunds
   - Two-person approval for refunds > $500 (V2)
   - Anomaly alert: Refund volume by agent

V1 NON-NEGOTIABLES:
    - No raw card numbers ever touch our servers (PCI scope avoidance)
    - Idempotency on all payment operations
    - Audit trail on all state transitions
    - Rate limiting on payment creation

V1 ACCEPTABLE RISKS:
    - Self-serve refund (not built; support-only for V1)
    - No two-person approval for large refunds (alert + audit trail instead)
```

---

# Part 14: System Evolution (Senior Scope)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVOLUTION PATH                                           │
│                                                                             │
│   V1 (Initial):                                                             │
│   - Single payment processor (Stripe)                                       │
│   - Auth + capture + refund flow                                            │
│   - PostgreSQL with synchronous replication                                 │
│   - Double-entry ledger with daily reconciliation                           │
│   - Idempotency at client and processor layers                              │
│   - State machine with audit trail                                          │
│   Scale: 100K orders/day, single currency (USD)                             │
│                                                                             │
│   V1.1 (First Issues — triggered by Stripe outage):                         │
│   - TRIGGER: 30-minute Stripe outage during peak; all payments failed       │
│   - FIX: Queue pending authorizations during outage; retry when recovered   │
│   - FIX: Circuit breaker on Processor Gateway (fail fast, not timeout)      │
│   - FIX: Hourly reconciliation (not just daily)                             │
│                                                                             │
│   V2 (Incremental — triggered by growth + business needs):                  │
│   - TRIGGER: Business wants to reduce processor fees; needs second processor│
│   - FIX: Multi-processor support (Stripe primary, Adyen fallback)           │
│   - TRIGGER: International expansion; need EUR and GBP                      │
│   - FIX: Multi-currency support (amount_cents + currency per payment)       │
│   - TRIGGER: Reconciliation job takes 2+ hours at 500K orders/day           │
│   - FIX: Streaming reconciliation (process as settlements arrive)           │
│                                                                             │
│   NOT IN SCOPE (Staff-level):                                               │
│   - Payment platform (self-service for multiple product teams)              │
│   - Cross-region payment routing                                            │
│   - Custom payment orchestration (split payments, marketplace payouts)      │
│   - ML-based fraud detection                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 15: Alternatives & Trade-offs

## Alternative 1: Synchronous Capture (Auth + Capture in One Step)

```
ALTERNATIVE: Combine authorization and capture into a single "charge" call.

WHAT IT IS:
    Instead of authorize → [ship] → capture, do a single "charge $49.99"
    that authorizes and captures atomically.

WHY CONSIDERED:
    - Simpler flow (one API call, not two)
    - No orphaned authorizations (no "authorized but never captured")
    - Fewer processor API calls (saves ~0.01% on fees)

WHY REJECTED FOR V1:
    - Cannot void a capture. If order is cancelled after charge, must refund.
    - Refund takes 5-10 business days to return to customer.
    - Authorization + delayed capture: void is instant (customer never sees charge).
    - Business requirement: Charge on shipment, not on order placement.
    - Regulatory: Some jurisdictions require charging only when value is delivered.

TRADE-OFF:
    Single charge: Simpler code, but worse customer experience on cancellation.
    Auth + capture: More complex, but correct for e-commerce (charge on delivery).

WHEN TO USE SINGLE CHARGE:
    Digital goods (instant delivery). No shipping delay. No cancellation window.
    Example: In-app purchase, subscription activation.
```

## Alternative 2: Event-Sourced Payment Store

```
ALTERNATIVE: Store payment state as a sequence of events, not mutable records.

WHAT IT IS:
    Instead of UPDATE payments SET status = 'captured', append an event:
    {type: "payment_captured", payment_id: 123, capture_id: "CAP_456", timestamp: ...}
    Reconstruct current state by replaying events.

WHY CONSIDERED:
    - Perfect audit trail (events ARE the data, not a separate table)
    - Enables event-driven architecture (subscribers react to events)
    - Natural fit for financial systems (append-only = immutable history)

WHY REJECTED FOR V1:
    - Query complexity: "What's the current status?" requires replaying all events
    - Debugging complexity: State is implicit, not explicit
    - Team expertise: Team knows PostgreSQL + relational; event sourcing is new
    - At 100K orders/day, a simple status column + audit table is sufficient
    
TRADE-OFF:
    Event sourcing: Architecturally elegant, operationally complex.
    State + audit table: Architecturally simple, operationally familiar.
    
    At V1 scale and team size: Simplicity wins. Event sourcing is a valid
    V3+ migration if the system becomes a platform.

WHEN TO RECONSIDER:
    If the team needs to replay historical events for analytics, if multiple
    services need to react to payment state changes, or if the audit
    requirement becomes more complex (regulatory event log).
```

---

# Part 16: Interview Calibration (L5 & L6)

## Staff vs Senior: Contrast

| Dimension         | Senior (L5) focus                            | Staff (L6) focus                                           |
|-------------------|----------------------------------------------|------------------------------------------------------------|
| **Scope**         | Single payment flow; correctness             | Cross-team contracts; Payment + Order + Finance handoffs   |
| **Blast radius**  | "What fails?"                                | "How far does it propagate? Who else is impacted?"         |
| **Judgment**      | Idempotency, ledger, reconciliation           | When to halt captures; when to escalate; risk acceptance   |
| **Cost**          | Processor fees vs infra                      | Cost of compliance failure; cost of trust loss             |
| **Teaching**     | Debugging payment bugs                       | How to teach others; leadership explanation of trade-offs  |

## What Interviewers Evaluate (L5)

| Signal | How It's Assessed |
|--------|-------------------|
| **Scope management** | Do they clarify auth-only vs auth+capture, single vs multi-currency? |
| **Correctness thinking** | Do they discuss idempotency, double-charge prevention, ledger invariant? |
| **Failure handling** | Do they address the ambiguous timeout problem? Processor outage? |
| **Financial awareness** | Do they mention double-entry, reconciliation, audit trail? |
| **Ownership mindset** | Do they think about on-call: "what if the ledger is imbalanced at 2 AM?" |

## How Google Interviews Probe This

```
COMMON FOLLOW-UP QUESTIONS:

1. "What happens if the processor times out?"
   → Tests: Understanding of the ambiguous response problem; check-before-retry

2. "How do you prevent double-charges?"
   → Tests: Two-layer idempotency (client + processor); state machine design

3. "How do you know the system is correct?"
   → Tests: Double-entry ledger, reconciliation, audit trail

4. "What if a refund fails?"
   → Tests: Retry strategy; manual fallback; customer communication

5. "Why not use Kafka for event-driven payments?"
   → Tests: ACID reasoning; correctness > throughput for money

6. "How do you handle a processor outage?"
   → Tests: Circuit breaker; graceful degradation; failover thinking
```

## Common L4 Mistakes

```
L4 MISTAKE 1: No idempotency

    L4: "We call Stripe to charge the card."
    WHY IT'S L4: What happens on retry? Network timeout? Double-click?
    Without idempotency keys, every retry is a new charge.
    L5 FIX: Two-layer idempotency. Client → Service (idempotency_key).
    Service → Processor (processor idempotency_key). Both deterministic.

L4 MISTAKE 2: Money stored as floating point

    L4: "Amount is a DECIMAL(10,2) or FLOAT."
    WHY IT'S L4: FLOAT introduces rounding. $49.99 * 100 = 4998.99999...
    DECIMAL is better but still allows $49.999. Integer cents: Always exact.
    L5 FIX: Integer cents. $49.99 = 4999. No ambiguity. Industry standard.

L4 MISTAKE 3: No internal ledger

    L4: "We check Stripe for the payment status."
    WHY IT'S L4: Single point of truth is an external system. Can't verify
    independently. Can't query revenue without Stripe API. Can't detect
    discrepancies. No local audit trail.
    L5 FIX: Internal double-entry ledger. Processor is verified against it.

L4 MISTAKE 4: Timeout treated as failure

    L4: "If Stripe times out, we return 'declined' to the user."
    WHY IT'S L4: Timeout ≠ failure. The charge may have succeeded.
    Telling the user "declined" and then charging them is the worst outcome.
    L5 FIX: Timeout = UNKNOWN. Check processor status. Never assume.
```

## Borderline L5 Mistakes

```
BORDERLINE L5 MISTAKE 1: Good idempotency but no reconciliation

    ALMOST L5: Handles double-charges, has state machine, but no mention
    of how to verify the system is actually correct over time.
    WHY BORDERLINE: Idempotency prevents most errors, but silent bugs
    (ledger drift, missed captures) are only caught by reconciliation.
    STRONG L5: "I reconcile daily against the processor settlement report.
    Any discrepancy > $0.01 triggers an alert."

BORDERLINE L5 MISTAKE 2: No discussion of what happens when the ledger is wrong

    ALMOST L5: Has ledger, has reconciliation, but doesn't discuss
    what to do when a discrepancy is found.
    WHY BORDERLINE: Detecting problems is half the battle. Fixing them
    (void, refund, manual adjustment) requires operational readiness.
    STRONG L5: "If the ledger shows a captured payment that the processor
    doesn't have: We may have recorded a capture that didn't actually
    happen. I'd check payment_events for the processor response, check
    the processor dashboard, and either add the missing processor record
    or reverse our ledger entry."
```

## Example Strong L5 Phrases

```
- "Before I start designing, let me clarify: auth-only or auth+capture? Single currency or multi?"
- "Money demands strong consistency. Every payment state transition is a linearizable operation."
- "The hardest problem isn't scale—it's the ambiguous timeout. I solve it with check-before-retry."
- "I'll use integer cents for all amounts. Floating point and money don't mix."
- "My ledger invariant is: sum(debits) = sum(credits). If that ever fails, I stop captures and investigate."
- "I reconcile against the processor daily. My system is correct only if it agrees with Stripe's records."
```

## Strong Senior Answer Signals

```
STRONG L5 SIGNALS:

1. "The payment state machine has explicit valid transitions. Any invalid
   transition returns 409 Conflict. You can't capture a declined payment."
   → Shows: State machine thinking, defensive design

2. "Idempotency keys are deterministic—derived from order_id, not random.
   A retry produces the same key, which is the entire point."
   → Shows: Deep understanding of idempotency (not surface-level)

3. "I use double-entry bookkeeping because it's a self-verifying data
   structure. If debits ≠ credits, there's a bug."
   → Shows: Financial system awareness, correctness thinking

4. "Processor timeout means UNKNOWN, not FAILED. I check the processor
   for the transaction status before retrying."
   → Shows: Production experience with ambiguous failures

5. "Infrastructure cost is $500/month. Processor fees are $5M/month.
   I'm not optimizing the $500."
   → Shows: Correct prioritization, business awareness

6. "The reconciliation job is the safety net for everything else. If
   idempotency has a bug, reconciliation catches it within 24 hours."
   → Shows: Defense in depth, operational maturity
```

## Staff-Level Probes (L6)

```
STAFF PROBES (beyond L5 correctness):

1. "Who gets paged when the ledger is imbalanced at 2 AM?"
   → Tests: Cross-team ownership; handoff protocol

2. "What's the blast radius of a ledger bug that deployed 30 minutes ago?"
   → Tests: Containment thinking; scope of impact

3. "How do you explain to a non-technical VP why we can't 'just retry faster'
   when the processor times out?"
   → Tests: Leadership communication; risk framing

4. "If Finance and Payment disagree on a reconciliation result, who wins?"
   → Tests: Ownership boundaries; escalation path

5. "How would you teach a new engineer on the team why idempotency keys
   must be deterministic?"
   → Tests: Teaching ability; transfer of judgment

6. "What's the cost of a 1-hour payment outage vs 1-hour of double-charges?"
   → Tests: Business prioritization; trust vs revenue
```

## Common Senior Mistake (When Staff Expects More)

```
SENIOR MISTAKE: "I have idempotency, ledger, and reconciliation. Correctness covered."

WHY IT'S INSUFFICIENT FOR STAFF:
- Correctness is necessary but not sufficient
- Staff expects: Who owns reconciliation when it fails? What's the handoff?
- Staff expects: Blast radius of a bug. How do you contain?
- Staff expects: How do you explain trade-offs to leadership?

STAFF PHRASE: "Correctness is table stakes. I also design for ownership boundaries,
blast radius containment, and escalation paths so the org can operate when it breaks."
```

## Staff Phrases: How to Teach & Explain to Leadership

```
TEACHING (to new engineer):
"I'll explain why idempotency keys must be deterministic. Imagine a retry
after a timeout. If the key includes a timestamp, the retry is a new key.
The processor sees it as a new transaction. Two charges. The fix: key = 
order_id + operation. Same every time. Retry = same key = same result."

LEADERSHIP EXPLANATION (why we can't "just retry faster"):
"Retrying faster when the processor times out increases the risk of double-charge.
The processor may have succeeded—we just didn't get the response. A fast retry
could send a second request before we know. We check first. That takes 30 seconds.
It's a trade-off: 30 seconds of delay vs 1% chance of double-charge. We choose
delay. Trust is harder to recover than a missed sale."
```

---

# Part 17: Diagrams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PAYMENT FLOW ARCHITECTURE                                │
│                                                                             │
│  ┌──────────┐   ┌──────────┐  ┌──────────┐                                  │
│  │ Frontend │   │  Order   │  │ Support  │                                  │
│  │ Checkout │   │ Service  │  │  Tool    │                                  │
│  └────┬─────┘   └────┬─────┘  └────┬─────┘                                  │
│       │ create       │ capture     │ refund                                 │
│       └──────────────┼─────────────┘                                        │
│                      ▼                                                      │
│        ┌──────────────────────────────┐                                     │
│        │       PAYMENT API (×2)       │  ← Stateless, LB'd                  │
│        │  Idempotency → State Machine │                                     │
│        │  → Validate → Persist        │                                     │
│        └──────────┬──────┬────────────┘                                     │
│                   │      │                                                  │
│          ┌────────┘      └────────┐                                         │
│          ▼                        ▼                                         │
│  ┌─────────────-──────┐   ┌───────────────────┐                             │
│  │    POSTGRESQL      │   │ PROCESSOR GATEWAY │                             │
│  │   (Primary +       │   │                   │                             │
│  │    Sync Standby)   │   │ Stripe adapter    │                             │
│  │                    │   │ Timeout handling  │                             │
│  │ payments           │   │ Retry + circuit   │                             │
│  │ ledger_entries     │   │ breaker           │                             │
│  │ refunds            │   └─────────┬─────────┘                             │
│  │ payment_events     │             │                                       │
│  │ reconciliation_log │             ▼                                       │
│  └────────────────────┘   ┌───────────────────┐                             │
│                           │   STRIPE / ADYEN   │                            │
│                           │  (External, 3rd    │                            │
│                           │   party processor) │                            │
│                           └───────────────────┘                             │
│                                                                             │
│  ASYNC PATHS:                                                               │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐                 │
│  │  Webhook     │   │ Reconciler   │   │  Receipt Email   │                 │
│  │  Dispatcher  │   │ (daily cron) │   │  Job (async)     │                 │
│  │  → Order Svc │   │ → Compare    │   │  → SendGrid      │                 │
│  │  → Notify    │   │   ledger vs  │   │                  │                 │
│  │              │   │   processor  │   │                  │                 │
│  └──────────────┘   └──────────────┘   └──────────────────┘                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Payment State Machine Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PAYMENT STATE MACHINE                                    │
│                                                                             │
│                                                                             │
│   ┌──────────┐                                                              │
│   │ created  │ ← Initial state (after DB insert)                            │
│   └────┬─────┘                                                              │
│        │                                                                    │
│        ├── Processor: authorized ──→ ┌────────────┐                         │
│        │                             │ authorized │                         │
│        │                             └──────┬─────┘                         │
│        │                                    │                               │
│        │                    ┌───────────────┼───────────────┐               │
│        │                    │               │               │               │
│        │                    ▼               ▼               ▼               │
│        │             ┌──────────┐   ┌──────────────┐  ┌─────────┐           │
│        │             │ captured │   │capture_failed│  │ voided  │           │
│        │             └─────┬────┘   └──────┬───────┘  └─────────┘           │
│        │                   │               │            (terminal)          │
│        │                   │               └── retry → captured             │
│        │                   │               └── give up → voided             │
│        │                   │                                                │
│        │                   ├── partial refund ──→ ┌─────────────────────┐   │
│        │                   │                      │partially_refunded   │   │
│        │                   │                      └──────────┬──────────┘   │
│        │                   │                                 │              │
│        │                   └── full refund ──→ ┌─────────────┴────────┐     │
│        │                                       │  fully_refunded      │     │
│        │                                       └──────────────────────┘     │
│        │                                        (terminal)                  │
│        │                                                                    │
│        ├── Processor: declined ──→ ┌──────────┐                             │
│        │                           │ declined │  (terminal)                 │
│        │                           └──────────┘                             │
│        │                                                                    │
│        └── Timeout exhausted ──→ ┌───────────────────────┐                  │
│                                  │ authorization_failed  │  (terminal)      │
│                                  └───────────────────────┘                  │
│                                                                             │
│   INVARIANTS:                                                               │
│   - Terminal states have no outgoing transitions                            │
│   - captured → voided is INVALID (must refund instead)                      │
│   - Only one active payment per order at a time                             │
│   - Ledger entries exist iff status = captured/refunded                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming & Senior-Level Exercises

---

## A. Scale & Load Thought Experiments

### Experiment A1: Flash Sale (10× Burst for 1 Hour)

```
SCENARIO: 10× orders/sec for 1 hour during promotional event

AT 10× (100 orders/sec, ~300 DB writes/sec):
    PostgreSQL: 300 writes/sec is trivial (< 5% capacity on r5.large)
    Payment API: 2 instances handle 100 requests/sec easily
    Processor (Stripe): 100 auth requests/sec is within standard rate limits
    
    BOTTLENECK: Not internal. Stripe rate limit may apply at higher scales.
    
    At 50× (500 orders/sec):
    Stripe default rate limit: ~100 requests/sec (negotiable)
    Need: Rate limit negotiation or queuing excess authorization requests

MOST FRAGILE ASSUMPTION: Processor rate limit, NOT internal capacity.
    Payment systems are correctness-bound, not throughput-bound.
```

### Experiment A2: Which Component Fails First

```
AT INCREASING SCALE:

1. PROCESSOR RATE LIMIT (FAILS FIRST)
   - Stripe default: ~100 req/sec (varies by account)
   - Mitigation: Negotiate higher limits; or multi-processor (Stripe + Adyen)
   
2. RECONCILIATION JOB DURATION (FAILS SECOND)
   - At 5M orders/day: Reconciling 5M records in one batch = hours
   - Mitigation: Streaming reconciliation; partition by date
   
3. DATABASE WRITE THROUGHPUT (FAILS THIRD, at very high scale)
   - At 10,000 orders/sec (3× Amazon's peak): ~50,000 writes/sec
   - PostgreSQL on large instance: ~30,000 writes/sec
   - Mitigation: Shard by merchant or region
   
4. NOTHING ELSE FAILS before database write throughput.
   Payment systems are NOT high-throughput systems.
```

### Experiment A3: Vertical vs Horizontal

```
WHAT SCALES VERTICALLY:
    - PostgreSQL: Bigger instance handles more writes
    - Effect: 3× throughput for 2× cost (good deal)
    - Limit: Single-instance ceiling (~30,000 writes/sec)

WHAT SCALES HORIZONTALLY:
    - Payment API: Stateless; add instances behind LB
    - Webhook dispatcher: Stateless; add instances
    - Reconciliation: Partition by date range, parallel workers

WHAT DOES NOT SCALE (without architecture change):
    - Single processor (Stripe): Must add second processor
    - Single reconciliation job: Must partition or stream
```

---

## B. Failure Injection Scenarios

### Scenario B1: Slow Processor (10× Latency, Not Down)

```
SITUATION: Stripe authorization latency increases from 2s to 20s

IMMEDIATE BEHAVIOR:
- Users wait 20+ seconds on checkout page (terrible UX)
- Payment API threads occupied longer → thread pool exhaustion risk
- If thread pool exhausted: New requests queued or rejected

USER SYMPTOMS:
- Checkout "spinning" for 20+ seconds
- Some timeouts (our 5s timeout fires) → "Payment failed, try again"
- Users retry → more load on already-slow processor

DETECTION:
- processor_auth_latency_p99: 2s → 20s
- auth_timeout_rate: 0% → 60%
- Thread pool utilization: 20% → 95%

MITIGATION:
1. Circuit breaker opens at > 50% error rate → fail fast (< 1s instead of 20s)
2. User message: "Payments are temporarily slow. Please try again in a few minutes."
3. DO NOT increase timeout to 20s (would exhaust all threads)
4. Queue authorizations? No—user is waiting. Better to fail fast and retry later.

PERMANENT FIX:
- Async authorization with polling (user gets "processing..." and polls)
- Multi-processor failover (route to Adyen while Stripe is slow)
```

### Scenario B2: Repeated Worker Crashes (Reconciliation OOM)

```
SITUATION: Reconciliation job loads all 5M daily records into memory. OOM.

IMMEDIATE BEHAVIOR:
- Reconciliation job crashes
- Daily reconciliation doesn't run
- Discrepancies not detected

USER SYMPTOMS:
- None immediately
- Discrepancies accumulate undetected
- Finance team asks: "Why no reconciliation report today?"

DETECTION:
- Reconciliation job failure alert (cron monitor)
- OOM kill in container logs
- No reconciliation_log entry for today

MITIGATION:
1. Run reconciliation for smaller date ranges (hourly chunks)
2. Increase container memory as temporary fix
3. Fix: Streaming reconciliation (process in batches of 10K, not all at once)

PERMANENT FIX:
- Streaming/chunked reconciliation: Process 10K records at a time
- Cursor-based: SELECT ... WHERE id > last_processed_id LIMIT 10000
```

### Scenario B3: Cache Unavailability (Not Applicable)

```
SITUATION: V1 uses no cache for payment data. No impact.

WHY: Payment data must always be fresh. Caching introduces staleness risk
for financial records. This is a deliberate design choice.
```

### Scenario B4: Network Partition (API ↔ Processor)

```
SITUATION: 5% packet loss between Payment API and Stripe

IMMEDIATE BEHAVIOR:
- 5% of authorization requests timeout
- Retry with same idempotency key → most succeed on retry
- Some require 2-3 retries → total latency 10-15s
- Circuit breaker threshold not reached (error rate < 50%)

USER SYMPTOMS:
- ~5% of checkouts take 10-15 seconds instead of 3 seconds
- ~1% of checkouts fail after all retries (3× timeout)

DETECTION:
- processor_timeout_rate: 0% → 5%
- auth_latency_p99: 3s → 12s
- auth_retry_rate: 0.1% → 5%

MITIGATION:
- Retry with same idempotency key handles most cases
- Users who fail: Clear error message and retry button
- If packet loss is persistent (> 10 minutes): Investigate network path

PERMANENT FIX:
- Multiple network paths to processor (if available)
- Multi-processor: Failover to Adyen if Stripe connectivity degrades
```

### Scenario B5: Database Failover During Peak

```
SITUATION: PostgreSQL primary fails; synchronous standby promoted (10-second gap)

IMMEDIATE BEHAVIOR:
- All writes fail for ~10 seconds (create payment, update status)
- Processor calls in flight: Succeed at Stripe, but status update fails
- These are "limbo payments": Authorized at Stripe, unknown in our system

USER SYMPTOMS:
- 10 seconds of "Payment failed" errors
- Some users charged but shown failure (the dangerous case)

DETECTION:
- DB health check: Primary unreachable
- Failover event in DB orchestrator logs
- Spike in 503 errors from Payment API

MITIGATION:
1. Standby promoted automatically (managed PostgreSQL)
2. Payment API reconnects to new primary within seconds
3. CRITICAL: For limbo payments (authorized at Stripe, no local record):
   - Recovery job: Query Stripe for recent authorizations by our API key
   - For each Stripe auth without a matching local payment:
     Create the payment record, status = "authorized"
   - This is the reconciliation safety net saving us

PERMANENT FIX:
- Recovery job runs automatically after any failover event
- Immediate reconciliation (not just daily) after DB failover
- Monitoring: "Stripe authorizations without matching local payment"
```

### Scenario B6: Retry Storm After Processor Recovery

```
SITUATION: Stripe was down for 5 minutes. 3,000 authorization attempts queued.
Stripe recovers. All 3,000 retry simultaneously.

IMMEDIATE BEHAVIOR:
- 3,000 requests hit Stripe in < 10 seconds
- Stripe rate limit: 100/sec → 2,900 rejected (429 Too Many Requests)
- Rejected requests retry → more 429s → more retries → storm

USER SYMPTOMS:
- Even after Stripe recovers, payments still failing (rate limited)
- Users see "Payment failed" for another 5-10 minutes

DETECTION:
- processor_429_rate spikes
- Auth success rate remains low despite Stripe status "healthy"

MITIGATION:
1. Exponential backoff with jitter on retries (already designed in)
2. Global rate limiter on processor requests (max 80/sec, under Stripe's limit)
3. Drain queued requests gradually, not all at once

PERMANENT FIX:
- Token bucket rate limiter per processor: Max N requests/sec
- Queued requests dispatched at controlled rate
- Circuit breaker: Don't close instantly; ramp up gradually (50% → 80% → 100%)
```

---

## C. Cost & Operability Trade-offs

### Exercise C1: Biggest Cost Driver

```
BIGGEST COST DRIVER: Processor fees ($5.25M/month at 3M transactions)

Infrastructure ($500/month) is <0.01% of processor cost.
Optimizing infrastructure is irrelevant.

REAL COST OPTIMIZATIONS:
1. Negotiate processor rate: 2.9% → 2.5% = $600K/year saved
2. Reduce chargebacks: Each dispute costs $15-25 in fees + lost revenue
3. Reduce failed authorizations: Each failure = abandoned cart = lost revenue
4. Void unused authorizations promptly (some processors charge for auth holds)
```

### Exercise C2: 30% Cost Reduction

```
30% COST REDUCTION ON INFRASTRUCTURE:

Current infrastructure: $500/month

Option A: Single PostgreSQL instance (drop standby) → Save $175
    Risk: Data loss on primary failure (UNACCEPTABLE for payments)
    Recommendation: ABSOLUTELY NOT

Option B: Smaller API instances → Save $30
    Risk: Less headroom during peak
    Recommendation: Marginal savings, not worth the risk

REALITY: You cannot meaningfully reduce infrastructure cost for a payment
system at this scale. The budget is $500/month. Cutting 30% saves $150.
That's one hour of engineering time. Not worth optimizing.

WHERE TO ACTUALLY CUT COSTS:
- Processor fee negotiation (saves $50K-600K/year)
- Reduce chargebacks through better fraud prevention (saves $10K-100K/year)
- These are 1000× more impactful than infrastructure optimization
```

### Exercise C3: Cost of an Hour of Downtime

```
COST OF PAYMENT SYSTEM DOWNTIME:

Direct revenue loss:
    100K orders/day ÷ 24 hours = 4,167 orders/hour
    Average order: $50
    Lost revenue: 4,167 × $50 = $208,350/hour
    
    Reality: Not all customers abandon. Some retry.
    Estimated loss rate: 30-50% of attempted orders
    Estimated loss: $62K - $104K per hour

Indirect costs:
    - Customer trust damage (hard to quantify)
    - Support ticket surge (cost: $5-10 per ticket × hundreds of tickets)
    - Potential chargebacks from limbo transactions ($15-25 each)
    - Engineering investigation time (2-4 engineers × hours)

THIS IS WHY:
    - Payment creation availability target is 99.95%
    - Synchronous replication is non-negotiable
    - Processor failover is a V2 priority
    - Every design decision favors correctness and availability
```

---

## D. Ownership Under Pressure

### Exercise D0: 2 AM On-Call — Ledger Imbalance Alert

```
SCENARIO: 30-minute mitigation window

You're on-call. 2:17 AM. PagerDuty fires:
"CRITICAL: Ledger imbalance detected. Sum(debits) ≠ Sum(credits). Delta: $1,247.03"

This is the most dangerous alert in the payment system. It means money
is unaccounted for. Every minute that passes, more transactions may
compound the error.

QUESTIONS:

1. WHAT DO YOU CHECK FIRST?
   
   a. Identify the scope:
      SELECT payment_id FROM ledger_entries
      GROUP BY payment_id
      HAVING SUM(CASE WHEN entry_type='DEBIT' THEN amount_cents ELSE 0 END) !=
             SUM(CASE WHEN entry_type='CREDIT' THEN amount_cents ELSE 0 END);
      → How many payments are imbalanced? 1? 100? 10,000?
   
   b. Check timing: When did the imbalance start?
      Look at created_at of the first imbalanced entry.
      → Recent (last hour)? Likely a code deployment.
      → Gradual (over days)? Likely a subtle bug.
   
   c. Check recent deployments:
      Was anything deployed in the last 2 hours? If yes: prime suspect.
   
   d. Check payment_events for affected payments:
      Are they captures without matching ledger credits?
      Are they refunds without matching ledger reversals?

2. WHAT DO YOU EXPLICITLY AVOID TOUCHING?
   
   - DO NOT manually edit ledger_entries (immutable; corrections are new entries)
   - DO NOT halt the entire payment system (captures in flight will create
     more orphaned records if the fix isn't ready)
   - DO NOT run ad-hoc UPDATE queries on payments table
   - DO NOT restart services blindly (may lose in-flight processor responses)

3. ESCALATION CRITERIA
   
   - Delta > $10,000: Wake up the team lead immediately
   - Delta growing (not static): Halt new captures (prevent more damage)
   - Root cause unclear after 15 minutes: Escalate to senior oncall
   - Any sign of external compromise (unexpected refunds): Escalate to security
   
   If delta is static and small (1-5 payments):
   → Likely a single code bug affecting one flow
   → Investigate, don't escalate immediately

4. HOW DO YOU COMMUNICATE STATUS?
   
   - T+5 min: Post in #payments-incidents:
     "Investigating ledger imbalance. Delta: $1,247. Scope: [N] payments.
      No customer impact confirmed yet. Investigating root cause."
   - T+15 min: Update with root cause hypothesis:
     "Root cause: Refund handler deployed at 1:45 AM missing ledger write.
      Halting refund processing. Working on correcting entries."
   - T+30 min: Resolution or escalation:
     "Correcting entries written. Ledger balanced. Refund handler rolled back.
      Monitoring for 1 hour before marking resolved."
```

### Exercise D0b: 2 AM On-Call — Double-Charge Alert

```
SCENARIO: PagerDuty: "Double-charge detected. Order #5678 has 2 auth codes."

1. WHAT DO YOU CHECK FIRST?
   - How many orders are affected? (one-off vs systemic)
     SELECT order_id, COUNT(*) FROM payments GROUP BY order_id HAVING COUNT(*) > 1;
   - Was the idempotency key the same or different?
   - Check recent deployments and code changes to idempotency key generation

2. WHAT DO YOU EXPLICITLY AVOID?
   - DO NOT void both authorizations (void the SECOND one only)
   - DO NOT refund (authorization hold ≠ charge; void releases the hold)
   - DO NOT disable the payment system (handle affected orders individually)

3. ESCALATION CRITERIA
   - > 50 affected orders: Wake up team lead
   - Active (still happening): Halt new authorizations via feature flag
   - Customer contact: Loop in support team for proactive outreach

4. IMMEDIATE ACTIONS
   - Void the second authorization for each affected order
   - If both already captured: Refund the second capture immediately
   - Verify fix: Process a test payment and confirm single authorization
   - Customer communication: "A temporary hold will be released within 3-5 days"
```

---

## E. Correctness & Data Integrity

### Exercise E1: Idempotency Under Retries

```
QUESTION: User double-clicks "Pay." Two identical POST /payments requests
arrive 200ms apart. What happens?

ANSWER:
    Request 1: INSERT INTO payments (..., idempotency_key='order-1234-pay') → Success
    Request 2: INSERT ... idempotency_key='order-1234-pay' → CONFLICT
    → SELECT * FROM payments WHERE idempotency_key='order-1234-pay'
    → Return existing payment (same payment_id, status "created")
    
    Net effect: One payment. Second request returns the same result.
    
    But what about the authorization?
    Request 1 proceeds to authorize. Request 2 returns without authorizing.
    Authorization uses processor idempotency_key = "order-1234-auth"
    Even if somehow both requests reach the processor:
    → Processor sees same key → returns cached result.
    → One authorization. One charge.
```

### Exercise E2: Detecting Ledger Imbalance

```
QUESTION: How do you detect if the ledger is wrong?

ANSWER:
    Daily invariant check:
    
    SELECT
        SUM(CASE WHEN entry_type = 'DEBIT' THEN amount_cents ELSE 0 END) as debits,
        SUM(CASE WHEN entry_type = 'CREDIT' THEN amount_cents ELSE 0 END) as credits
    FROM ledger_entries;
    
    IF debits ≠ credits:
        1. ALERT IMMEDIATELY (this is P0)
        2. HALT all new captures (prevent further damage)
        3. Find the imbalanced entry:
           SELECT payment_id FROM ledger_entries
           GROUP BY payment_id
           HAVING SUM(CASE WHEN entry_type='DEBIT' THEN amount_cents ELSE 0 END) !=
                  SUM(CASE WHEN entry_type='CREDIT' THEN amount_cents ELSE 0 END);
        4. Inspect the payment: What happened? Missing credit? Extra debit?
        5. Write correcting entry (never edit existing entries)
        6. Resume captures after verification
    
    This should NEVER happen in normal operation. If it does, it's a bug.
```

### Exercise E3: Preventing Corruption During Partial Failure

```
QUESTION: Processor captures successfully. DB transaction for status update
+ ledger write fails (disk full). What happens?

ANSWER:
    Timeline:
    T=0: Processor captures $49.99 (money moved, irreversible)
    T=1: BEGIN; UPDATE payments; INSERT ledger_entries; → DISK FULL → ROLLBACK
    T=2: Payment still shows "authorized" in our DB
    T=3: Money is at Stripe but we don't know it
    
    Detection:
    - Reconciliation (daily): Stripe says "captured $49.99" for this payment.
      Our ledger says "authorized" (no capture). DISCREPANCY.
    - Alert: "Captured at processor but not in ledger"
    
    Recovery:
    1. Fix disk space (or DB issue)
    2. Manually or programmatically: Update payment to "captured" + write ledger entry
    3. Verify: Ledger now matches Stripe
    
    WHY this is safe:
    - Money moved at Stripe (irreversible)
    - We're behind, not ahead (our ledger is missing an entry)
    - Adding the entry corrects our books
    
    DANGEROUS REVERSE: Our ledger says "captured" but Stripe says "authorized"
    → We think we have money we don't. Would need to re-capture or void.
    → This is harder to handle. Prevention: Write ledger ONLY after confirmed capture.
```

---

## F. Incremental Evolution & Ownership

### Exercise F1: Adding Multi-Currency (2 Weeks)

```
REQUIRED CHANGES:
- payments table: currency field already exists (currently always 'USD')
- Validation: Accept 'EUR', 'GBP', 'USD'
- Processor gateway: Pass currency to Stripe (already supported by Stripe)
- Ledger entries: Already have currency field
- Reconciliation: Group by currency
- Display: Frontend shows correct currency symbol

RISKS:
- Currency mismatch: Order in EUR, payment in USD → wrong amount
- Reconciliation: Must compare within same currency, not across
- Refund: Must refund in same currency as capture

DE-RISKING:
- Validate: Payment currency must match order currency (enforced in API)
- Reconciliation: Add currency to GROUP BY
- Testing: Staging tests with EUR and GBP processors
```

### Exercise F2: Adding Second Processor (Adyen as Fallback)

```
REQUIRED CHANGES:
- Implement AdyenProcessor (implements PaymentProcessor interface)
- Processor selector: Route based on rules (primary: Stripe, fallback: Adyen)
- Configuration: Processor routing rules (% split or failover)
- Reconciliation: Run for both processors

RISKS:
- Different processor behaviors (Stripe auth expires in 7 days, Adyen in 30)
- Different error codes (must normalize to internal codes)
- Idempotency keys: Must be processor-specific (Stripe key ≠ Adyen key)

DE-RISKING:
- Shadow mode: Send 1% of traffic to Adyen, compare results with Stripe
- Normalize: AdyenProcessor maps Adyen responses to same internal format
- Gradual rollout: 1% → 5% → 20% → 50%
```

### Exercise F3: Safe Schema Migration (Adding Payment Method Type)

```
SCENARIO: Need to add payment_method_type column ('card', 'bank_transfer', 'wallet')

SAFE PROCEDURE:

Phase 1: Add nullable column
    ALTER TABLE payments ADD COLUMN payment_method_type VARCHAR(32);
    (Instant in PostgreSQL; no table rewrite)

Phase 2: Deploy code that writes new column
    New payments: payment_method_type = 'card' (all V1 payments are cards)
    Existing payments: NULL (acceptable for now)

Phase 3: Backfill existing rows
    UPDATE payments SET payment_method_type = 'card'
    WHERE payment_method_type IS NULL;
    (Batch: 10K rows per transaction)

Phase 4: Add NOT NULL constraint
    ALTER TABLE payments ALTER COLUMN payment_method_type SET NOT NULL;
    (Only after backfill complete)

ROLLBACK:
    Phase 1-2: Drop column (ALTER TABLE ... DROP COLUMN; fast)
    Phase 3-4: Column exists but is unused → no harm
```

---

## G. Deployment & Rollout Safety

### Rollout Strategy

```
DEPLOYMENT STRATEGY: Rolling with canary (payment systems get extra caution)

STAGES:
    1% → 1 API instance (canary)
    Bake time: 30 minutes (longer than typical due to financial risk)
    
    10% → 2 instances
    Bake time: 30 minutes
    
    50% → half fleet
    Bake time: 1 hour
    
    100% → full fleet

CANARY CRITERIA:
    - Authorization success rate ≥ baseline
    - No new ledger imbalance
    - No double-charge alerts
    - Processing latency within 10% of baseline
    - No new DLQ entries for payment operations

ROLLBACK TRIGGER:
    - ANY ledger imbalance (immediate rollback, P0)
    - Double-charge alert (immediate rollback, P0)
    - Auth success rate drops > 2% (investigate, rollback if not explained)
    - Error rate for any payment operation > 5% (rollback)

ROLLBACK TIME:
    Single instance: ~2 minutes
    Full fleet: ~15 minutes (rolling)
```

### Scenario: Bad Code Deployment

```
SCENARIO: New code has a bug: refund handler doesn't write reverse ledger entry

1. CHANGE DEPLOYED
   - New refund code rolled out to 1% (canary)
   - Expected: Refund creates reverse ledger entries (DEBIT revenue, CREDIT refund_payable)
   - Actual: Refund succeeds at Stripe, but ledger write skipped (code bug)

2. BREAKAGE TYPE
   - Subtle: Refund "works" (Stripe returns money), but ledger is wrong
   - Sum of debits ≠ sum of credits (revenue over-reported)
   - Not caught immediately (no crash, no error)

3. DETECTION SIGNALS
   - Ledger balance check: sum(debits) ≠ sum(credits) → ALERT (30-minute check interval)
   - Reconciliation: Stripe shows refund; ledger doesn't → DISCREPANCY
   - Canary: If only 1 refund processed during canary period, may not trigger

4. ROLLBACK STEPS
   - Halt rollout at canary
   - Rollback to previous version
   - Identify affected refunds: Refunds in Stripe without matching ledger entries
   - Write correcting ledger entries for each affected refund
   - Verify: sum(debits) = sum(credits) again

5. GUARDRAILS ADDED
   - Post-refund check: Verify ledger entries exist for refund_id immediately after commit
   - Integration test: Refund test asserts ledger entry count
   - Ledger balance check frequency: Every 30 minutes (catch within one canary bake period)
```

### Rushed Decision Scenario

```
RUSHED DECISION SCENARIO

CONTEXT:
- Launch in 1 week. Business insists on payment flow.
- Ideal: Full reconciliation, multi-processor, circuit breaker.
- Time for: Core auth + capture + ledger. Nothing else.

DECISION MADE:
- No reconciliation job (reconcile manually via Stripe dashboard for V1)
- No circuit breaker (rely on timeout + retry)
- No automated refund (support uses Stripe dashboard; log in our system manually)

WHY ACCEPTABLE:
- Low volume at launch (~100 orders/day). Manual reconciliation feasible.
- Stripe is highly reliable (99.99%); circuit breaker overkill at launch volume.
- Refunds are rare at launch; support team can handle 1-2/day manually.

TECHNICAL DEBT INTRODUCED:
- Manual reconciliation stops scaling at ~1,000 orders/day (2-3 weeks post-launch)
- No circuit breaker: If Stripe has a bad day, users wait for timeouts
- Manual refunds: Audit trail gap (Stripe refund not linked to our ledger)

PAYDOWN PLAN:
- Week 2: Build automated reconciliation job (most critical)
- Week 4: Build refund API (links refunds to ledger)
- Week 8: Add circuit breaker (depends on incident frequency)

COST OF CARRYING DEBT:
- One missed reconciliation discrepancy (caught late) = potential $500-5,000 loss
- One manual refund error = wrong amount refunded = customer complaint
- Acceptable for 2-4 weeks; unacceptable beyond that
```

---

## H. Interview-Oriented Thought Prompts

### Prompt H1: Clarifying Questions to Ask First

```
1. "Is this auth-only or auth+capture? Digital goods or physical goods?"
   → Determines: Single-step charge vs two-step flow

2. "What payment methods do we support? Card only, or also bank transfer, wallet?"
   → Determines: Processor integration complexity

3. "What's the order volume? Hundreds/day or millions/day?"
   → Determines: Whether PostgreSQL is sufficient, whether reconciliation is batch or stream

4. "Single currency or multi-currency?"
   → Determines: Schema and reconciliation complexity

5. "Do we need to support partial refunds?"
   → Determines: Refund data model, total_refunded_cents tracking

6. "What's the processor? Stripe, Adyen, custom bank integration?"
   → Determines: API reliability, idempotency support, timeout behavior
```

### Prompt H2: What You Explicitly Don't Build

```
1. FRAUD DETECTION (V1)
   "Fraud detection is a separate system. It runs before payment initiation.
   By the time a payment reaches our flow, fraud check has passed."

2. SUBSCRIPTION BILLING
   "Recurring charges, plan management, and dunning are a different system.
   Subscriptions USE this payment flow but don't define it."

3. MULTI-CURRENCY (V1)
   "V1: USD only. Multi-currency adds FX risk, settlement complexity, and
   regulatory requirements that aren't justified at launch volume."

4. SPLIT PAYMENTS / MARKETPLACE PAYOUTS
   "Splitting a payment between multiple merchants is marketplace logic.
   Different system, different regulatory requirements (money transmission)."

5. EXACTLY-ONCE PROCESSING
   "At-least-once with idempotent operations. Exactly-once across our system
   and the processor is impractical. Idempotency keys give us the same
   user-visible guarantee."
```

### Exercise I: Staff-Level — Cross-Team Handoff (L6)

```
SCENARIO: Reconciliation report shows $2,400 discrepancy. Ledger says we captured
$2,400 more than the processor's settlement report. Finance and Payment disagree
on who should investigate.

QUESTIONS:
1. Who owns the investigation? (Payment: we wrote the ledger. Finance: they own revenue numbers.)
2. What's the escalation path if the root cause is unclear after 4 hours?
3. How do you document the handoff so the next shift knows the state?
4. What's the blast radius if this is a code bug? (All payments since last deploy?)

STAFF ANSWER:
- Primary: Payment team (we own the code and ledger writes)
- Finance: Validates corrections before they're applied; signs off on manual adjustments
- Escalation: If root cause unclear after 4h, involve team lead; if > $10K, involve VP
- Handoff: Incident ticket with "Investigating: X. Next step: Y. Blocked by: Z."
- Blast radius: Query first imbalanced payment's created_at; all payments after last deploy before that time are suspect
```

### Prompt H3: Pushing Back on Scope Creep

```
INTERVIEWER: "What about supporting cryptocurrency payments?"

L5 RESPONSE: "I'd push back on crypto for V1. Cryptocurrency adds:
1. A fundamentally different settlement model (blockchain confirmation
   times, not instant)
2. Price volatility (payment amount changes between initiation and settlement)
3. Different regulatory requirements (varies by jurisdiction)
4. A new processor integration with different failure modes

For V1, I'd focus on card payments through Stripe. If crypto is a business
requirement, I'd treat it as a separate payment method type with its own
processor adapter—but that's V2, not V1."
```

---

# Final Verification

## Master Review Check (11 Items)

| # | Check | Status |
|---|-------|--------|
| 1 | **Scope & clarity** — Payment flow end-to-end; component responsibilities clear | ✓ |
| 2 | **Trade-offs justified** — Auth+capture vs single charge; PostgreSQL vs event sourcing | ✓ |
| 3 | **Failure handling** — Ambiguous timeout, processor outage, DB failover, retry storm | ✓ |
| 4 | **Scale analysis** — Concrete numbers; processor rate limit as first bottleneck | ✓ |
| 5 | **Real incident** — Structured table (Context\|Trigger\|Propagation\|User-impact\|Engineer-response\|Root-cause\|Design-change\|Lesson) | ✓ |
| 6 | **Staff vs Senior contrast** — Judgment, blast radius, cross-team, teaching | ✓ |
| 7 | **Cost drivers** — Processor fees dominant; compliance/trust costs acknowledged | ✓ |
| 8 | **Mental models / one-liners** — Memorable phrases; how to teach | ✓ |
| 9 | **Diagrams** — Architecture; state machine | ✓ |
| 10 | **Interview calibration** — L5 probes, L4 mistakes, Staff probes, Staff phrases | ✓ |
| 11 | **Exercises & Brainstorming** — Scale, failure, cost, ownership, correctness, evolution | ✓ |

## L6 Dimension Table (A–J)

| Dim | Dimension | Coverage | Notes |
|-----|-----------|----------|-------|
| **A** | Judgment | ✓ | State machine, conservative defaults, check-before-retry; Staff: when to halt, escalate |
| **B** | Failure/blast-radius | ✓ | Failure modes; blast radius table; containment strategy |
| **C** | Scale/time | ✓ | 100K orders/day; processor rate limit; time-to-detect via reconciliation |
| **D** | Cost | ✓ | $5.25M processor vs $500 infra; cost of downtime; Staff: trust loss |
| **E** | Real-world-ops | ✓ | 2 AM scenarios; double-charge; rollout; rushed decision |
| **F** | Memorability | ✓ | Mental model; one-liners; how to teach |
| **G** | Data/consistency | ✓ | Double-entry; ledger invariant; reconciliation |
| **H** | Security/compliance | ✓ | PCI scope avoidance; audit trail; abuse vectors |
| **I** | Observability | ✓ | Misleading signals; real signals; ledger balance alert |
| **J** | Cross-team | ✓ | Ownership table; handoff protocol; Finance/Payment boundaries |

---

## Senior-Level Signals (L5)

```
✓ This chapter MEETS Google Senior Software Engineer (L5) expectations.

SENIOR-LEVEL SIGNALS COVERED:

A. Design Correctness & Clarity:
✓ End-to-end: Create → Authorize → Capture → Ledger → Reconciliation
✓ Component responsibilities clear (Payment API, Processor Gateway, Ledger Writer)
✓ State machine with explicit valid transitions (incl. disputed, chargebacked, auth_expired)
✓ Double-entry bookkeeping with invariant checking
✓ Processor inbound webhooks (chargebacks, disputes, async events)

B. Trade-offs & Technical Judgment:
✓ Auth+capture vs single charge (justified for e-commerce)
✓ PostgreSQL vs event sourcing (simplicity wins at V1)
✓ Strong consistency for payments, eventual for notifications
✓ Two-layer idempotency (client → service, service → processor)
✓ Explicit non-goals (fraud, subscriptions, multi-currency)

C. Failure Handling & Reliability:
✓ Ambiguous timeout scenario (realistic production failure, full post-mortem)
✓ Conservative defaults (unknown = don't charge)
✓ Circuit breaker on processor gateway
✓ Reconciliation as safety net for all other failures
✓ DB failover + limbo payment recovery
✓ Orphaned authorization detection & cleanup (hourly job, 6-day threshold)
✓ Processor-initiated state changes (chargebacks/disputes via inbound webhooks)

D. Scale & Performance:
✓ Concrete numbers (100K orders/day, 50 writes/sec peak, 100 GB/year)
✓ Scale growth table (1×-50×)
✓ Correctness-bound, not throughput-bound (key insight)
✓ Processor rate limit as first bottleneck (not DB)

E. Cost & Operability:
✓ $500/month infrastructure vs $5.25M/month processor fees
✓ Correct prioritization (negotiate processor rate, not optimize DB)
✓ Misleading signals table (auth success rate, capture rate, revenue)
✓ On-call alerts (ledger imbalance, double-charge, reconciliation discrepancy)

F. Ownership & On-Call Reality:
✓ Double-charge incident scenario with 7-step response
✓ 2 AM on-call pressure scenario: Ledger imbalance (4 questions answered)
✓ 2 AM on-call pressure scenario: Double-charge alert (4 questions answered)
✓ Rollout stages with canary (30-min bake for financial system)
✓ Bad code deployment scenario (missing ledger entries)
✓ Rushed decision scenario (launch without reconciliation)

G. Concurrency & Correctness:
✓ State machine transitions via atomic UPDATE + WHERE status = expected
✓ Two-layer idempotency with pseudo-code
✓ Race conditions (double-capture, timeout retry, concurrent refund)
✓ Integer cents for money (no floating point)

H. Interview Calibration:
✓ L4 mistakes (no idempotency, FLOAT money, no ledger, timeout = failure)
✓ Borderline L5 mistakes (no reconciliation, no ledger imbalance response)
✓ Strong L5 signals and phrases
✓ Clarifying questions and non-goals

Brainstorming (Part 18):
✓ Scale: Flash sale, component failure order, vertical vs horizontal
✓ Failure: Slow processor, OOM reconciliation, network partition, DB failover, retry storm
✓ Cost: Biggest driver (processor fees), 30% reduction (irrelevant), downtime cost ($208K/hr)
✓ Ownership: 2 AM ledger imbalance scenario, 2 AM double-charge scenario
✓ Correctness: Double-click idempotency, ledger imbalance detection, partial failure corruption
✓ Evolution: Multi-currency, second processor, schema migration
✓ Deployment: Rollout stages, bad code scenario, rushed decision
✓ Interview: Clarifying questions, explicit non-goals, scope creep pushback
✓ Staff exercise: Cross-team handoff (Exercise I)
```
