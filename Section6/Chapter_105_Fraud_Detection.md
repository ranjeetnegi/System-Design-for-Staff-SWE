# Chapter 94: Fraud Detection — Stripe / PayPal / Uber at Scale

> Fraud detection is the only system design problem where being slow is as bad as
> being wrong. A 200ms latency budget, a 0.1% false positive rate that locks out
> real customers, and adversaries who actively probe your system to find gaps.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Fraud detection systems are mandatory knowledge at fintech companies (Stripe, PayPal,
Braintree, Square, Affirm) and appear at companies with payment flows (Uber, Airbnb,
Amazon, DoorDash). The system combines: real-time ML scoring in the request path,
rule engines, velocity checks, and a feedback loop from labeled fraud data.
Increasingly expected at L6 even at companies not primarily in fintech.

---

## Planned Content

### Part 1: The Problem Space
- Payment fraud: stolen cards, account takeover, chargeback fraud
- Account fraud: fake accounts, bot signups, promo abuse
- Transaction fraud: money laundering, synthetic identity fraud
- The adversarial nature: fraudsters probe your system and adapt
- Business trade-off: false positives (blocking real users) vs. false negatives (fraud losses)
  - A 1% false positive rate on 1B transactions = 10M legitimate transactions blocked
  - Stripe's public target: < 0.1% false positive rate, < 0.1% fraud rate

### Part 2: Rule Engines — The First Line of Defense
- Hard rules: block if velocity > threshold, block known bad IPs/cards, require 3DS
- Rule examples:
  - "If same card used 5+ times in 1 minute → block"
  - "If billing address country ≠ IP country → flag for review"
  - "If new account + high-value transaction → require OTP"
- Rule engines: Drools, custom DSL, or code-as-config
- Trade-off: rules are interpretable and fast; they're also easy for fraudsters to reverse-engineer
- Real incident: Uber 2016 promo abuse — $70M in fraudulent credits claimed because
  the promo code rule had a gap that fraudsters found within hours

### Part 3: Velocity Checks (Real-Time Counters)
- "How many transactions has this card done in the last 60 seconds?"
- Sliding window counter: Redis ZSET with timestamp-scored entries
  - ZRANGEBYSCORE to count recent events, ZADD to add new event, ZREMRANGEBYSCORE to trim
  - Memory: ~50 bytes per event × 1000 events × 100M users = 5TB — must be selective
- Approximate counting: Count-Min Sketch for high-cardinality keys (IP addresses)
- Feature dimensions: per-card, per-account, per-device, per-IP, per-merchant
- Time windows: 1 minute, 1 hour, 1 day, 7 days — each a separate counter

### Part 4: ML Scoring in the Request Path
- Model: gradient boosted trees (XGBoost/LightGBM) or neural network
- Input features: 100–1000 features computed at request time
  - Transaction features: amount, merchant category, time of day, currency
  - User features: account age, historical fraud rate, typical spend pattern
  - Device features: device fingerprint, IP reputation, geolocation
  - Velocity features (from Part 3): recent transaction counts
- Latency budget: feature computation 10ms + model inference 5ms = 15ms total
- Model output: fraud probability score (0.0–1.0)
- Score thresholds: < 0.3 → auto-approve; 0.3–0.7 → step-up auth; > 0.7 → block

### Part 5: Feature Store (Online + Offline)
- Online feature store: low-latency lookup of pre-computed user/card features
  - Redis: account_age, historical_fraud_rate, avg_transaction_amount
  - Updated in real-time as transactions happen
- Offline feature store: batch-computed features updated nightly
  - Graph features: is this merchant connected to known fraudulent merchants?
  - Behavioral features: typical transaction hour, typical merchant category
- Training-serving skew: features at training time must match features at serving time
  (the biggest ML engineering challenge in production fraud systems)

### Part 6: Feedback Loop and Model Retraining
- Labels: transactions are labeled fraud/not-fraud after chargebacks or manual review
- Label latency: chargebacks take 30–90 days → model trained on stale labels
- Near-real-time signals: if a card is reported stolen, retroactively label recent
  transactions from that card as fraud
- Retraining pipeline: weekly/daily → evaluate on held-out set → A/B test → deploy
- Model drift: fraud patterns shift; model needs continuous retraining
- Real incident: PayPal 2020 — pandemic shifted spending patterns so dramatically
  that their fraud model's false positive rate doubled in 2 weeks, blocking millions
  of legitimate transactions

### Part 7: Graph-Based Fraud Detection
- Fraud rings: groups of fake accounts working together
- Graph: users, devices, cards, IP addresses, merchants as nodes; transactions as edges
- Fraud signal: highly connected cluster of nodes with high fraud rate
- Algorithms: community detection, label propagation, graph neural networks
- Real-time vs. offline: graph algorithms are expensive → run offline, apply results online
- Real incident: Stripe 2019 — graph analysis revealed a fraud ring of 10,000
  synthetic identities sharing 47 device fingerprints and 12 IP addresses

### Part 8: Human Review Queue
- Not all suspicious transactions can be auto-decided: some go to human review
- Queue prioritization: high-value transactions first, time-sensitive transactions first
- Reviewer interface: transaction details, user history, fraud signals, similar cases
- Reviewer feedback: labeled decisions feed back into model training
- SLA: review decisions within 15 minutes for transactions above $10,000

### Part 9: Interview Framework
- Always clarify: payment fraud vs. account fraud vs. promo abuse (different systems)
- Layer the defenses: rules → velocity checks → ML score → human review
- Key trade-off: latency vs. accuracy (better model = slower inference)
- Key trade-off: false positives vs. false negatives (business cost vs. fraud loss)
- L5 vs. L6: L5 says "use ML"; L6 designs the feature store architecture, explains
  training-serving skew, describes the feedback loop with label latency problem,
  and discusses the graph-based fraud ring detection system separately

---

## The One-Sentence Summary

> "Fraud detection = layered defense (rules → velocity checks → ML score → human review) with a feature store serving 100+ signals in < 15ms, a feedback loop with 30-90 day label latency, and a separate offline graph analysis for fraud ring detection — the adversarial nature means the system must be treated as a continuous arms race, not a shipped feature."

---

*Full chapter: ~2,500 lines. Pairs with Ch70 (Payment Systems) and Ch41a (ML System Design).*
