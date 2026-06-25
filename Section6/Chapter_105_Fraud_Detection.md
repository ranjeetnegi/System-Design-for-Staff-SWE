# Chapter 94: Fraud Detection — Stripe / PayPal / Uber at Scale

> Fraud detection is the only system design problem where being slow is as bad as
> being wrong. A 200ms latency budget, a 0.1% false positive rate that locks out
> real customers, and adversaries who actively probe your system to find gaps.

---

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AT-A-GLANCE                                     │
│                                                                         │
│  PROBLEM: Detect fraudulent transactions in real time with:             │
│    - < 200ms added latency in the payment path                          │
│    - < 0.1% false positive rate (real users blocked)                    │
│    - < 0.1% false negative rate (fraud slipping through)                │
│    - Adaptive to adversaries who probe and evolve tactics               │
│                                                                         │
│  CORE ARCHITECTURE — LAYERED DEFENSE:                                   │
│    Layer 1: Hard rules (IP blocklist, known stolen cards) — < 1ms       │
│    Layer 2: Velocity checks (rate counters per card/IP/user) — 5ms      │
│    Layer 3: ML scoring (gradient boosted trees, 100+ features) — 15ms   │
│    Layer 4: Human review queue (for scores in the gray zone)            │
│    Layer 5: Offline graph analysis (fraud ring detection, nightly)      │
│                                                                         │
│  KEY COMPONENTS:                                                        │
│    Feature store:   online (Redis, < 5ms) + offline (batch, 24h lag)   │
│    Rule engine:     Drools or custom DSL; hundreds of configurable rules│
│    ML model:        XGBoost/LightGBM; 100–1000 features; 5ms inference │
│    Feedback loop:   chargebacks (30-90d lag) → labels → retrain weekly  │
│    Graph analysis:  community detection on transaction graph (Spark)    │
│                                                                         │
│  KEY NUMBERS:                                                           │
│    Stripe volume:   ~500M+ transactions/day = ~6,000/sec                │
│    Feature budget:  10ms feature fetch + 5ms inference = 15ms ML total  │
│    Label latency:   30–90 days (chargeback cycle)                       │
│    Review SLA:      15 minutes for transactions > $10,000               │
│    Model retrain:   weekly (fast drift) to daily (active fraud campaign)│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: The Fraud Detection Problem

### What Is Fraud?

Fraud in a payments context is not a single thing. "Fraud" covers several distinct attack
types that require different detection strategies:

**Payment fraud** — The most common type. A stolen credit card number is used to make
purchases before the real cardholder notices. The fraudster buys high-value goods (gift
cards, electronics) or transfers funds before the card is canceled.

```
PAYMENT FRAUD LIFECYCLE:
  Card stolen (skimming, phishing, dark web purchase)
       ↓
  Fraudster tests the card with a small transaction ($1 coffee)
       ↓
  If it works, makes large purchases immediately (before card is canceled)
       ↓
  Real cardholder notices → calls bank → chargeback
       ↓
  Merchant loses the merchandise AND pays a chargeback fee (~$25-50)
```

**Account takeover (ATO)** — A real user's account credentials are stolen (via phishing,
credential stuffing, or password reuse). The attacker logs in and changes the linked
payment method or makes purchases. Harder to detect than payment fraud because the login
is from a legitimate account.

**Promo abuse** — Users create multiple fake accounts to claim referral bonuses or first-order
discounts multiple times. Uber's 2016 promo abuse incident cost ~$70M when fraudsters used
device farms to claim ride credits through fabricated referral chains.

**Money laundering / structuring** — Criminals use a payments platform to move illegally-
obtained money (layering: many small transactions to obscure origin). Regulated by AML
(Anti-Money Laundering) laws; compliance failure = massive fines.

**Synthetic identity fraud** — An attacker creates a fake identity using a combination of
real and fabricated information (real SSN from a credit-inactive person + fake name).
Builds credit slowly over months, then "busts out" — takes all available credit at once.
Hardest type to detect.

### The Core Trade-off: False Positives vs. False Negatives

Every fraud detection decision is a trade-off:

```
FALSE NEGATIVE: A fraudulent transaction is approved.
  Business cost: loses the transaction value, pays chargeback fee, damages reputation
  Cost per incident: $100-$10,000+

FALSE POSITIVE: A legitimate transaction is blocked.
  Business cost: lost sale, frustrated customer, possible churn
  Cost per incident: $5-100 (lost sale) + ongoing brand damage
  
Stripe's stated target: < 0.1% fraud rate, < 0.1% false positive rate
  On 500M transactions/day: 500,000 transactions flagged incorrectly per day even at 0.1%
  That's 500,000 real customers denied per day — business-critical to minimize this.

The precision-recall trade-off:
  Tighten threshold → fewer fraud through, more real customers blocked (high precision, low recall)
  Loosen threshold → more fraud through, fewer real customers blocked (low precision, high recall)
  
  The right threshold depends on the business: a $5 coffee shop can afford a higher false
  positive rate. A $50,000 wire transfer system must be extremely precise.
```

### The Adversarial Nature: The Arms Race

This distinguishes fraud detection from most other ML problems. A fraud detection system
is not deployed against a static distribution. Fraudsters actively probe the system:

1. Buy a stolen card on the dark web.
2. Make a small test transaction. Approved? → Scale up. Blocked? → Try a different card.
3. Once blocked, probe what triggers the block: amount? merchant type? IP address? velocity?
4. Adjust tactics to avoid detection.
5. Share successful techniques with other fraudsters.

This means a fraud model trained on historical data becomes less effective over time —
the fraudsters have already learned to avoid the patterns the model was trained on. The
model must be retrained continuously and the feedback loop (covered in Part 6) is critical.

Real consequence: Stripe, PayPal, and others invest more engineering effort in the feedback
loop and model retraining pipeline than in the original model itself.

### 5-Level Progression: Understanding the Problem

**Intern:** "Fraud detection = flag suspicious transactions. Use a blocklist of known bad cards
and a rule like 'block if amount > $10,000.'"

**Junior Engineer:** "You need velocity checks: 'Has this card been used 5 times in the last
minute?' and an ML model that scores each transaction. Combine both signals."

**Mid-level Engineer:** "The system has layers: hard rules (instant blocklist), velocity counters
(Redis with sliding windows), ML model (XGBoost, 100 features, 5ms inference), and a review
queue for gray-zone scores. The key engineering challenge is getting all features to the model
within a 15ms budget."

**Senior Engineer:** "Fraud detection is a streaming ML problem. The core tension is between
accuracy (more features, more complex models) and latency (< 200ms total). You solve this
with a pre-computed feature store: features that are expensive to compute (user behavioral
history, graph features) are computed offline and cached in Redis. Only fast, real-time
features (transaction amount, merchant, current velocity) are computed live. The feedback
loop has a 30-90 day label latency problem — chargebacks take months, so the model is
always trained on stale ground truth."

**Staff Engineer:** "Fraud detection at Stripe/PayPal scale has three distinct subsystems
that must be designed together but have different requirements. First, the real-time scoring
system: must be < 200ms, must handle 6,000 transactions/second, must serve 100+ features
within a 15ms budget. This is a latency-sensitive distributed system design problem. Second,
the feature store: must bridge online serving (Redis, sub-5ms) and offline computation (Spark,
daily). Training-serving skew — when features in training look different from features at
serving time — is the single biggest source of model degradation in production. Third, the
feedback loop: the 30-90 day label latency means the model is always outdated. The mitigation
is multi-signal: chargebacks (slow but certain), manual review decisions (fast), card-stolen
signals from issuing banks (near-real-time via Visa/Mastercard APIs). The staff-level insight
is that the system architecture must be designed to minimize training-serving skew, not just
to maximize model accuracy on the training set."

---

## Part 2: Rule Engines — The First Line of Defense

Rules are the simplest and most interpretable layer of fraud detection. They run before
the ML model and can block obviously fraudulent transactions with zero ML latency.

### Hard Rules

```
EXAMPLES OF HARD RULES:
  BLOCK if card_number in known_stolen_cards_set      -- blocklist lookup
  BLOCK if ip_address in known_proxy_ips              -- proxy/VPN detection
  BLOCK if billing_country != ip_geo_country          -- geo mismatch
  BLOCK if card_bin in high_risk_bins                 -- certain card issuers are fraud-prone
  REQUIRE_3DS if transaction_amount > $500             -- step-up authentication
  REQUIRE_3DS if new_account AND transaction_amount > $100
  BLOCK if velocity_1min_per_card > 5                 -- 5 transactions in 60 seconds
  BLOCK if velocity_1hr_per_device > 20               -- device velocity
  FLAG_REVIEW if merchant_category = "gift_cards" AND amount > $100
```

Rules are stored in a rules database and evaluated by a rules engine (open-source:
Drools; or custom DSL like Stripe's Stripe Radar). Rules are interpretable and can be
quickly updated when a new fraud pattern is discovered.

```
RULE ENGINE ARCHITECTURE:
  Transaction arrives
       ↓
  Rules Engine: evaluate all active rules in priority order
       ↓
  Results: [rule_id, action, triggered: true/false] for each rule
       ↓
  If any BLOCK rule triggered → return decline immediately (< 1ms)
  If any FLAG rule triggered → append flag to transaction context, continue to ML
  If REQUIRE_3DS triggered → return 3DS challenge to client
  Else → pass to velocity checks
```

### Rule Management and Velocity

Rules are not static. The rules management system must:
- Allow non-engineers (fraud analysts) to write and deploy new rules without code changes
- Support rule versioning and rollback
- Measure rule performance: hit rate, false positive rate, fraud caught per rule
- A/B test new rules in shadow mode (evaluate but don't act) before going live

**Rules fatigue:** Too many rules creates conflicts and makes the system brittle. Good
rule hygiene: regular review and pruning of low-signal rules, consolidation of overlapping
rules, and a hard cap on active rule count (say, 500 rules max).

### 5-Level Progression: Rule Engines

**Intern:** "Write rules in code as a big if-else statement. If the transaction matches any
fraud pattern, block it."

**Junior Engineer:** "Rules in code are hard to update. I'd store rules in a database and
evaluate them with a rules engine like Drools. This lets fraud analysts add new rules without
a code deploy."

**Mid-level Engineer:** "I'd add rule performance tracking. Each rule has metrics: how many
transactions it fires on, how many of those turn out to be fraud, how many turn out to be
legitimate. Rules with low precision (lots of false positives) get tuned or disabled. Shadow
mode: run new rules for 24 hours without acting on them — just log results — before promoting
to active."

**Senior Engineer:** "The rules engine needs circuit breakers. If a misconfigured rule starts
blocking 50% of traffic (a real incident at PayPal in 2019), there must be a kill switch that
disables any rule immediately without a deployment. I'd add an automatic kill switch: if any
single rule fires on > X% of traffic in a rolling 5-minute window, auto-disable it and page
the on-call fraud engineer."

**Staff Engineer:** "Rule engines are ML's complement, not its replacement. Rules handle the
known, high-confidence cases (stolen cards from known sources, impossible geolocation) where
ML adds no value — you don't need probabilistic scoring when you know with certainty a card
is stolen. ML handles the ambiguous, probabilistic cases that rules can't capture. The
architecture must separate these cleanly: rules run first (< 1ms), produce hard decisions
for obvious cases, and produce context signals (list of triggered rule IDs) for the ML model
as additional features. The ML model sees both the transaction features and the rule context,
making it more powerful than either system alone."

---

## Part 3: Velocity Checks — Real-Time Counters

Velocity checks answer the question: "How many times has this entity done X in the last
Y minutes?" They are critical for detecting card testing (try a stolen card with small
amounts) and account takeover (rapid transactions after login from new device).

### Sliding Window Counters

```
VELOCITY CHECK EXAMPLES:
  transactions_1min_per_card_number     - card being tested?
  transactions_1hr_per_card_number      - unusual activity?
  transactions_1day_per_account         - behavioral change?
  unique_merchants_1hr_per_card         - card used across many merchants quickly?
  transactions_1min_per_ip_address      - bot/scripted attack?
  failed_auth_15min_per_account         - brute force?
  new_payees_1hr_per_account            - account takeover sending to new recipients?
  high_value_transactions_24hr_per_user - sudden large spending?
```

**Implementing sliding window in Redis:**

```
APPROACH 1: REDIS SORTED SET (exact sliding window)
  Key:    velocity:{dimension}:{entity_id}  e.g., velocity:card:4111111111111111
  Value:  ZSET where member = transaction_id, score = unix_timestamp_ms
  
  On new transaction:
    ZADD velocity:card:{card_id} {now_ms} {txn_id}       -- add event
    ZREMRANGEBYSCORE velocity:card:{card_id} -inf {now_ms - window_ms}  -- trim old
    ZCARD velocity:card:{card_id}                         -- count in window
  
  Memory per key: ~50 bytes × events_in_window
  For 1000 events/minute window: 1000 × 50 = 50KB per active card
  For 100M active cards: 50KB × 100M = 5TB -- too expensive!
  
  Solution: Only track entities that have had activity recently.
  Set TTL = window_size + 60s. Inactive cards' keys auto-expire.
  Active fraud attack: maybe 1M active cards at peak = 50GB -- manageable.

APPROACH 2: REDIS STRING (fixed window, cheaper)
  Key:    velocity:{dimension}:{entity_id}:{minute_bucket}
  Value:  integer count
  
  INCR velocity:card:{card_id}:{unix_minute}
  EXPIRE velocity:card:{card_id}:{unix_minute} 120  -- keep for 2 windows
  
  To count the last N minutes, fetch N keys and sum. Much cheaper memory.
  Trade-off: not exact (counts from the start of the minute, not rolling 60 seconds).
  Good enough for most fraud signals.

APPROACH 3: COUNT-MIN SKETCH (approximate, memory-efficient)
  For very high-cardinality dimensions (IP addresses: billions of unique IPs):
  Count-Min Sketch uses a fixed-size bitmap with multiple hash functions.
  Memory: ~4KB for 1M entries with < 1% error.
  Use for IP velocity, device fingerprint velocity where exact counts aren't needed.
```

### Feature Dimensions for Velocity

```
ENTITY TYPES:
  card_number      -- the payment instrument
  card_bin         -- first 6 digits (identifies the issuing bank)
  account_id       -- the platform's user account
  device_id        -- fingerprinted device
  ip_address       -- network location
  billing_email    -- email used for billing
  merchant_id      -- the merchant receiving payment
  
TIME WINDOWS:
  1 minute    -- card testing, brute force attempts
  5 minutes   -- slightly longer attack windows
  1 hour      -- behavioral anomalies, account takeover
  1 day       -- daily spending patterns
  7 days      -- longer-term pattern changes
  30 days     -- monthly baseline

COMBINATION: ~8 entities × 5 windows = ~40 velocity features per transaction
  All computed from Redis in a single pipeline call (MULTI/EXEC): ~5ms total
```

---

## Part 4: ML Scoring in the Request Path

The ML model is the brain of the fraud detection system. It takes 100+ features and
produces a single fraud probability score (0.0 = definitely legitimate, 1.0 = definitely fraud).

### Feature Categories

```
TRANSACTION FEATURES (computed from the current request — no lookup needed):
  transaction_amount
  transaction_amount_log     -- log transform; skewed distribution
  merchant_category_code     -- MCC: 5411 = grocery, 6012 = financial institution
  is_card_present            -- physical swipe vs. online entry
  is_international           -- billing country ≠ merchant country
  day_of_week                -- weekend transactions have different patterns
  hour_of_day                -- 3am transactions are anomalous for most users
  billing_zip_distance_from_ip  -- in km; large = suspicious

VELOCITY FEATURES (from Redis, Part 3):
  txn_count_1min_card
  txn_count_1hr_card
  unique_merchants_1hr_card
  failed_auths_15min_account
  ... (all 40 velocity dimensions)

USER/ACCOUNT FEATURES (from online feature store, pre-computed):
  account_age_days
  total_lifetime_transaction_count
  avg_transaction_amount_30d
  stddev_transaction_amount_30d
  historical_fraud_rate          -- rare: only if user has prior fraud
  typical_merchant_categories    -- encoded: does this merchant category match usual?
  typical_transaction_hour       -- does this time of day match usual?
  is_email_verified
  phone_number_age_days

DEVICE FEATURES (from device fingerprinting service):
  device_id                      -- unique fingerprint
  device_age_days                -- how long has this device been seen?
  device_fraud_rate              -- how often does this device appear in fraud?
  is_emulator                    -- mobile emulators are used for fraud
  is_vpn_or_proxy                -- privacy tools also used for fraud
  ip_reputation_score            -- third-party feed (Maxmind, IPQualityScore)

CARD FEATURES (from card issuer BIN lookup + history):
  card_bin_fraud_rate            -- this issuing bank's overall fraud rate
  card_age_days                  -- how long has this card been in our system?
  card_countries_used_30d_count  -- 1 country = normal; 10 countries = suspicious
```

### Model Architecture

```
MODEL: Gradient Boosted Decision Tree (XGBoost or LightGBM)
  
  Why not deep learning?
  - GBTs are faster to serve (microseconds per inference vs. milliseconds for neural nets)
  - GBTs are interpretable (feature importance; explain why a transaction was blocked)
  - GBTs work well on tabular data with mixed feature types
  - GBTs are robust to missing features (a device fingerprint not available → impute)
  
  Deep learning is used for:
  - Sequence models: model the temporal sequence of a user's transactions (LSTM/Transformer)
  - Embedding models: represent users, merchants, cards as dense vectors for similarity

MODEL SERVING:
  Model artifact: serialized XGBoost model (~50MB)
  Hosted in: dedicated inference service (MLflow, Seldon, or custom Go/Rust service)
  Hardware: CPU inference (no GPU needed for GBT); 50 cores → ~10,000 inference/sec
  Latency: < 5ms for 100 features on a single core

THRESHOLDS:
  Score < 0.3  → Auto-approve (no action)
  0.3 – 0.5   → Log + monitor (unusual but not suspicious)
  0.5 – 0.7   → Step-up authentication (OTP via SMS/email)
  0.7 – 0.9   → Hold for human review
  Score > 0.9  → Auto-block immediately
  
  Thresholds are per-merchant, per-channel, per-country — not global.
  A $1 transaction has a higher tolerance; a $50,000 wire has almost zero.
```

### Latency Budget

```
REQUEST TIMELINE (total budget: 200ms from payment form submission):
  
  TLS + load balancer          →   5ms
  Rule engine evaluation       →   1ms
  Redis velocity lookups (40)  →   5ms  (pipelined: ~1 round trip)
  Online feature store fetch   →   5ms  (Redis batch GET, ~30 features)
  Feature engineering (code)   →   3ms
  ML inference                 →   5ms
  Decision logic + logging     →   2ms
  
  FRAUD DETECTION TOTAL:       →  21ms
  
  Remaining budget for:
    Payment network (Visa/MC)  → 100ms
    Authorization response     →  10ms
    Application overhead       →  69ms
    
  Total:                       → 200ms budget ✓

The 21ms fraud detection budget is achievable with Redis pipelining
(send all 40+ GET commands in one network round trip) and efficient
feature engineering code (pre-compiled, no JSON parsing in the hot path).
```

---

## Part 5: Feature Store — Online + Offline

The feature store is the infrastructure that makes 100+ features available within 5ms.
It is the hardest engineering challenge in production fraud detection.

### The Training-Serving Skew Problem

```
TRAINING ENVIRONMENT:
  Model trained on 6 months of historical transactions.
  Features computed from the full historical database.
  Example: user's avg_transaction_amount_30d computed from all transactions in training set.

SERVING ENVIRONMENT:
  At prediction time, you need the SAME features, but only using information
  available at the time of the transaction (no future data!).
  
  The trap: at training time, avg_transaction_amount_30d is easy to compute
  (just look at the previous 30 days in the dataset). At serving time, you need
  a pre-computed rolling 30-day average that's been maintained continuously.
  
  If the training computation differs from the serving computation in ANY way
  (different time window, different data source, different aggregation logic),
  the model performance in production will be worse than in offline evaluation.
  This gap is training-serving skew, and it's the #1 cause of ML systems
  underperforming in production relative to offline metrics.

SOLUTION: Feature pipeline parity
  The SAME code that computes features for serving must also compute features for training.
  Use a streaming feature computation system (Flink or Spark Streaming) that:
    1. At serving time: computes features from the live event stream, stores in Redis
    2. At training time: replays the historical event stream, computes the same features
  This guarantees serving and training use identical logic.
```

### Feature Store Architecture

```
ONLINE FEATURE STORE (Redis — < 5ms):
  Purpose: serve real-time features at inference time
  Contents: pre-computed user/card/device features, updated by streaming pipeline
  Keys:
    user_features:{user_id}     → HSET with 20+ fields (account_age, fraud_rate, etc.)
    card_features:{card_id}     → HSET with 10+ fields (bin_fraud_rate, age, etc.)
    device_features:{device_id} → HSET with 10+ fields (reputation, age, etc.)
  Access: Redis HMGET, fetch all features for 3 entities in one pipeline = 3 round trips → 5ms
  Consistency: eventual (features updated by Kafka consumers, < 1s lag)

OFFLINE FEATURE STORE (S3 + Spark — 24h lag):
  Purpose: compute expensive features that can't be computed in real time
  Contents: graph features (connected to known fraudulent merchants), 
            long-term behavioral baselines (180-day averages), 
            ML embeddings (user represented as a 64-dim vector)
  Update: nightly Spark job; results written to Redis by the morning
  
  These features are valuable but stale. A user's "connected to fraud ring" score
  from yesterday is still useful; it doesn't need sub-second freshness.

FEATURE PIPELINE (Kafka + Flink):
  Kafka: receives all transaction events in real time
  Flink: streaming computation of velocity features, rolling averages
  Output: writes computed features back to online feature store (Redis)
  
  Key guarantee: the Flink computation is also run on historical data for training,
  ensuring training-serving parity.
```

### 5-Level Progression: Feature Store

**Intern:** "I'd compute features in the request handler: query MySQL for user history,
calculate averages, pass to the model."

**Junior Engineer:** "Querying MySQL on every request is too slow. Pre-compute user features
nightly and cache in Redis. At request time, fetch from Redis (< 1ms per key)."

**Mid-level Engineer:** "Nightly batch is too stale for velocity features. I'd use a streaming
feature pipeline (Flink) to update features in Redis as transactions happen. Batch for slow-
changing features (account age, long-term averages), streaming for fast-changing features
(velocity counters, recent transaction history)."

**Senior Engineer:** "The feature store must guarantee training-serving parity — the hardest
requirement. I'd implement 'point-in-time correct' feature serving: when training the model,
each historical transaction must use only features available at THAT transaction's timestamp
(no peeking at future data). This requires the feature store to maintain a history of feature
values, not just the current value. For training, I replay the event stream through the same
Flink computation as serving. The Flink job output is written to both Redis (serving) and
S3/Parquet (training dataset). The training dataset is guaranteed to match the serving
computation because they use the same code."

**Staff Engineer:** "Feature stores are a platform problem, not a per-model problem. Every
ML model at the company benefits from a centralized feature store that: (1) enforces point-
in-time correctness for training, (2) guarantees low-latency serving, (3) provides feature
lineage (which features influenced which model decisions — critical for regulatory compliance),
(4) enables feature reuse across models (don't recompute account_age for every model that
needs it). Companies like Uber (Michelangelo), Airbnb (Chronon), and LinkedIn (Frame) built
dedicated feature store platforms. The ROI comes from reducing feature engineering time across
the ML team, not from any single model's performance. The staff-level decision is to invest
in a centralized platform early, before every team builds their own incompatible feature
computation pipeline."

---

## Part 6: Feedback Loop and Model Retraining

### The Label Latency Problem

```
LABEL LIFECYCLE:
  Day 0:    Transaction occurs. Model scores it 0.42 (step-up auth). Customer completes OTP. Approved.
  Day 1:    Customer checks account. Doesn't recognize the charge.
  Day 2:    Customer calls bank. Bank opens dispute.
  Day 30:   Bank issues chargeback to merchant's payment processor.
  Day 45:   Payment processor notifies Stripe.
  Day 60:   Stripe receives final confirmation: this transaction was fraud.

Total label latency: 60 days from transaction to confirmed fraud label.

CONSEQUENCE:
  If you retrain your model today, the most recent labeled fraud example is 60 days old.
  Any new fraud technique introduced in the last 60 days is invisible to your model.
  Fraudsters can operate for up to 60 days without triggering model retraining.

MITIGATION — MULTI-SIGNAL LABELING:
  Signal 1: Chargebacks (ground truth, 30-90 day lag)
  Signal 2: Manual review decisions (same-day; human labeled this as fraud/not-fraud)
  Signal 3: Card stolen notifications (Visa/Mastercard provide near-real-time feed)
  Signal 4: Account flagged by user ("I didn't do this" = soft fraud signal)
  Signal 5: Pattern matching on known fraud signatures (new rule hits many recent txns)
  
  Combining these signals: use Signal 2-5 as "likely fraud" labels for recent data,
  Signal 1 as "confirmed fraud" for training. Weight certain labels higher in training.
```

### Retraining Pipeline

```
RETRAINING SCHEDULE:
  Weekly: standard retraining on last 6 months of data + recent labels
  Daily: if fraud rate increases > 20% from baseline (active fraud campaign detected)
  Immediate: if a new fraud pattern is confirmed by manual review team

RETRAINING PIPELINE:
  1. Export labeled transactions from data warehouse (S3/Snowflake)
  2. Point-in-time correct feature join: attach features as they existed at txn time
  3. Train model (XGBoost; ~2 hours on GPU cluster for 500M rows)
  4. Evaluate on held-out set: precision, recall, AUC-ROC
  5. Shadow mode deployment: new model scores all transactions but doesn't decide
  6. Compare new model vs. existing on last 24h of traffic
  7. If new model is better AND false positive rate is acceptable: promote
  8. Gradual rollout: 1% → 10% → 100% of traffic
  9. Monitor post-deploy: watch for false positive spike or fraud rate increase
  10. Full rollback in < 5 minutes if anomaly detected

MODEL VERSIONING:
  Store all model versions with metadata: training date, training data version, features used
  Keep last 3 versions deployable instantly (< 1 minute rollback)
  Archive older versions to S3 for audit/regulatory compliance (some regulations require
  explanability for fraud decisions for 7+ years)
```

### Model Drift Detection

```
DRIFT INDICATORS:
  Distribution drift: input feature distribution shifts (new merchant type becomes common)
    Detect: monitor feature distributions with statistical tests (KL divergence, KS test)
    
  Label drift: fraud rate changes (new attack vector; seasonal patterns)
    Detect: monitor daily fraud rate vs. rolling 90-day baseline
    
  Performance drift: model AUC decreases
    Detect: monitor AUC on labeled data weekly
    
  Concept drift: the relationship between features and labels changes
    (fraudsters learn to avoid old detection patterns)
    Detect: monitor false negative rate; manual review team noticing new fraud patterns
    
ACTION:
  Distribution drift: monitor, may need feature recalibration
  Label drift: immediate retraining if rate > 20% above baseline
  Performance drift: schedule retraining, investigate root cause
  Concept drift: highest priority — all-hands incident, add new signals/rules
```

---

## Part 7: Graph-Based Fraud Detection

Individual transaction scoring can't detect organized fraud rings. Graph analysis finds
structural patterns in the transaction network.

### The Fraud Ring Problem

```
FRAUD RING: 10,000 synthetic identities sharing:
  - 47 device fingerprints (each device used by 200+ "different" users)
  - 12 IP address ranges
  - 3 email domains (all newly registered)
  - Similar transaction timing patterns (all active 2am-4am)
  
No individual transaction looks suspicious:
  - Each account is new, so no historical fraud
  - Each transaction is small (<$500)
  - Velocity per account is low
  
But the GRAPH is suspicious:
  - 10,000 accounts all connected to the same 47 devices
  - High clustering coefficient within the ring
  - All accounts created in the same 2-week period
```

### Graph Construction

```
NODES:
  Users, devices, IP addresses, payment cards, email addresses, merchants

EDGES (from transactions + login events):
  user → device (this user used this device)
  user → ip (this user connected from this IP)
  user → card (this user paid with this card)
  user → email (registration email)
  card → merchant (this card was used at this merchant)

FRAUD SIGNAL ON EDGES:
  Edge weight = count of connections (user logged in from device X 5 times)
  Edge label = is any endpoint confirmed fraud?

GRAPH SIZE:
  500M transactions/day × 3-4 edges each = ~1.5B new edges/day
  Running total graph: ~1T edges (grows forever → need edge expiry: remove edges >1 year old)
```

### Fraud Detection Algorithms on the Graph

**Community detection:** Find clusters of densely connected nodes. A cluster where >5% of
nodes are confirmed fraud is a fraud ring candidate. Use Louvain algorithm or label
propagation on Spark GraphX.

**Label propagation:** If node A is confirmed fraud, propagate a "fraud proximity score"
to all nodes within 2 hops. Nodes adjacent to many fraud nodes get a high proximity score
even if they haven't been individually flagged.

```python
# Spark GraphX: label propagation pseudocode
def fraud_label_propagation(graph, num_iterations=3):
    # Initialize: confirmed fraud nodes get score 1.0, others 0.0
    scores = graph.vertices.withColumn("fraud_score", 
        when(col("is_confirmed_fraud"), 1.0).otherwise(0.0))
    
    for iteration in range(num_iterations):
        # For each node, average the fraud scores of neighbors
        messages = graph.aggregateMessages(
            sendMsg = lambda edge: edge.srcAttr["fraud_score"] * edge.attr["weight"],
            mergeMsg = lambda a, b: (a + b) / 2
        )
        # Update node scores: blend prior score with messages from neighbors
        scores = scores.join(messages).withColumn(
            "fraud_score", 
            col("fraud_score") * 0.3 + col("message") * 0.7
        )
    
    return scores
```

**Embedding-based detection:** Train a Graph Neural Network (GNN) that learns node
embeddings. Nodes that are structurally similar to known fraud nodes get similar embeddings.
Use cosine similarity between a new account's embedding and known fraud account embeddings
as a real-time fraud signal.

### Integration: Offline Scores to Online Scoring

```
OFFLINE PIPELINE (nightly Spark job):
  Input: transaction graph from last 90 days
  Compute: label propagation scores + community fraud rates + node embeddings
  Output: per-node fraud proximity score → write to Redis

ONLINE SERVING:
  At transaction time:
  "user_graph_fraud_score" = Redis GET graph_score:{user_id} → 0.23
  This score is added as one feature in the ML model (Part 4)
  
The graph score doesn't make real-time decisions — it's one feature among 100+.
It's particularly valuable as a "prior" that shifts the model's decision boundary
even when the individual transaction looks clean.
```

---

## Part 8: Human Review Queue

Not every transaction can be auto-decided. Scores in the 0.7-0.9 range go to human
reviewers who have additional context and judgment.

### Queue Design

```sql
CREATE TABLE review_queue (
    review_id        UUID        PRIMARY KEY,
    transaction_id   VARCHAR(64) NOT NULL,
    user_id          BIGINT      NOT NULL,
    fraud_score      FLOAT       NOT NULL,
    amount           DECIMAL(12,2) NOT NULL,
    currency         CHAR(3)     NOT NULL,
    merchant_name    VARCHAR(255) NOT NULL,
    enqueued_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    sla_deadline     TIMESTAMP   NOT NULL,  -- enqueued_at + SLA based on amount
    priority         INT         NOT NULL,  -- higher amount = higher priority
    assigned_to      BIGINT      NULL,      -- reviewer user_id
    status           ENUM('PENDING','IN_REVIEW','DECIDED') NOT NULL DEFAULT 'PENDING',
    decision         ENUM('APPROVE','DECLINE','ESCALATE') NULL,
    decided_at       TIMESTAMP   NULL,
    INDEX idx_status_priority (status, priority DESC, enqueued_at ASC)
);
```

**Priority calculation:**

```python
def compute_priority(amount, fraud_score, is_first_offense):
    base = math.log(amount + 1)  # log scale: $100 and $10K are both high
    urgency = fraud_score        # higher score = more urgent
    recidivism = 2.0 if is_first_offense else 1.0  # first-time unusual = more careful
    return base * urgency * recidivism
```

**SLA by amount:**

```
Amount < $100:       Review within 4 hours  (low cost; auto-decline if SLA missed)
$100 – $10,000:      Review within 2 hours
> $10,000:           Review within 15 minutes  (high cost; escalate if SLA missed)
```

### Reviewer Interface

The reviewer sees:
- Transaction details (amount, merchant, time, IP, device)
- User account history (account age, prior purchases, prior disputes)
- Fraud signals (which rules fired, ML score, top 5 feature contributions)
- Similar historical transactions and their outcomes
- One-click approve/decline/escalate with free-text notes

**Feature contribution display (SHAP values):**

```
WHY THIS TRANSACTION WAS FLAGGED (fraud score: 0.83):
  
  Unusual time of day (3:42am)                    +0.15
  Device is new (first seen 2 hours ago)          +0.23
  IP address is a known VPN exit node             +0.18
  Merchant is a gift card seller                  +0.12
  Amount is 12× user's typical transaction        +0.08
  
  Offsetting:
  Account is 3 years old (usually trustworthy)    -0.08
  User has verified phone number                  -0.05
  
COMPARABLE HISTORICAL TRANSACTIONS:
  [2024-01-05] Similar device, similar amount, similar time → was FRAUD
  [2024-01-08] Same merchant category, new device           → was FRAUD
```

This interface is built on SHAP (SHapley Additive exPlanations), a technique for
explaining ML model decisions. Required by regulations in some jurisdictions (EU AI Act
requires explainability for automated credit decisions).

---

## Part 9: DB Schema Reference

```sql
-- Core transaction table (simplified; real table has 50+ columns)
CREATE TABLE transactions (
    txn_id          UUID        PRIMARY KEY,
    user_id         BIGINT      NOT NULL,
    card_id         BIGINT      NOT NULL,
    merchant_id     BIGINT      NOT NULL,
    amount          DECIMAL(12,2) NOT NULL,
    currency        CHAR(3)     NOT NULL,
    status          ENUM('APPROVED','DECLINED','REVIEW','CHARGEBACK') NOT NULL,
    fraud_score     FLOAT       NULL,       -- NULL if not scored (e.g., below threshold)
    fraud_label     BOOLEAN     NULL,       -- NULL until labeled; TRUE = confirmed fraud
    label_source    VARCHAR(50) NULL,       -- 'chargeback', 'manual_review', 'card_stolen'
    labeled_at      TIMESTAMP   NULL,
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_card_created (card_id, created_at DESC),
    INDEX idx_unlabeled (fraud_label) WHERE fraud_label IS NULL
);

-- Rule engine audit log
CREATE TABLE rule_decisions (
    txn_id      UUID        NOT NULL,
    rule_id     INT         NOT NULL,
    rule_name   VARCHAR(100) NOT NULL,
    triggered   BOOLEAN     NOT NULL,
    action      ENUM('BLOCK','FLAG','REQUIRE_3DS','NONE') NOT NULL,
    evaluated_at TIMESTAMP  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (txn_id, rule_id)
);

-- Fraud model predictions
CREATE TABLE model_predictions (
    txn_id       UUID     PRIMARY KEY,
    model_version VARCHAR(50) NOT NULL,
    fraud_score  FLOAT    NOT NULL,
    features_json TEXT    NOT NULL,  -- serialized feature values (for audit/debugging)
    predicted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Chargebacks (source of fraud labels)
CREATE TABLE chargebacks (
    chargeback_id    UUID        PRIMARY KEY,
    txn_id           UUID        NOT NULL,
    amount           DECIMAL(12,2) NOT NULL,
    reason_code      VARCHAR(10) NOT NULL,  -- Visa/MC reason code
    received_at      TIMESTAMP   NOT NULL,
    status           ENUM('RECEIVED','DISPUTED','CONFIRMED') NOT NULL,
    INDEX idx_txn (txn_id)
);
```

---

## Part 10: API Design

```
FRAUD SCORING API (internal; called synchronously in payment path):

POST /v1/fraud/score
Body:
{
  "transaction_id": "txn_abc123",
  "user_id": 12345,
  "card_id": 67890,
  "amount": 149.99,
  "currency": "USD",
  "merchant_id": 999,
  "merchant_category_code": 5411,
  "ip_address": "203.0.113.42",
  "device_fingerprint": "df_xyz789",
  "billing_country": "US",
  "timestamp": "2024-01-15T03:42:00Z"
}

Response (< 200ms):
{
  "transaction_id": "txn_abc123",
  "fraud_score": 0.83,
  "decision": "REVIEW",            // APPROVE | STEP_UP_AUTH | REVIEW | BLOCK
  "triggered_rules": ["R042_LATE_NIGHT_NEW_DEVICE", "R017_GIFT_CARD_MERCHANT"],
  "latency_ms": 18,
  "model_version": "v2024-01-10"
}

FEEDBACK API (async; called when fraud label is confirmed):
POST /v1/fraud/label
Body:
{
  "transaction_id": "txn_abc123",
  "is_fraud": true,
  "label_source": "chargeback",
  "labeled_at": "2024-03-15T10:00:00Z"
}

Response: 202 Accepted (async; queued for model training pipeline)
```

---

## Part 11: Interview Application — L5 vs L6

### "Design a fraud detection system for a payments company."

```
L5 ANSWER (30-40 minutes):
  ✓ Requirements: < 200ms latency, < 0.1% false positive rate
  ✓ Layered defense: rules → velocity checks → ML score
  ✓ Rule engine: blocklists, velocity thresholds
  ✓ Velocity counters in Redis (sliding window or fixed window)
  ✓ ML model: XGBoost with 50-100 features
  ✓ Feature categories: transaction, velocity, user history
  ✓ Score thresholds: auto-approve / step-up auth / block
  ✓ Feedback loop: chargebacks → labels → retrain
  ✓ Human review queue for ambiguous cases

L6 ADDITIONAL DEPTH:
  ✓ Feature store architecture: online (Redis, < 5ms) + offline (Spark, 24h)
  ✓ Training-serving skew: how to guarantee feature computation parity
  ✓ Label latency problem: 30-90 day chargeback cycle; mitigation strategies
  ✓ Graph-based fraud ring detection: node types, label propagation, offline pipeline
  ✓ Model drift detection: distribution drift, concept drift, automated retraining triggers
  ✓ SHAP explainability for regulatory compliance and reviewer interface
  ✓ Rule engine circuit breakers and shadow mode for safe rule deployment
  ✓ Capacity planning: 6,000 TPS at Stripe scale; Redis pipelining for latency budget
  ✓ Model versioning and rollback: < 5 minute rollback SLA
```

### L5 vs L6 Calibration Table

```
TOPIC                          L5 EXPECTED                 L6 EXPECTED
───────────────────────────────────────────────────────────────────────────
System layers                  Rules + ML + review         Same + graph analysis offline
Velocity counters              Redis INCR or ZSET          Sliding window vs fixed window; Count-Min
Feature store                  Pre-compute in Redis        Online + offline; training-serving skew
ML model                       "Use XGBoost"               Feature budget; inference latency; drift
Feedback loop                  Chargebacks → retrain       Label latency; multi-signal labeling
Graph fraud                    "Use graph analysis"        Label propagation; offline Spark pipeline
Explainability                 Not mentioned               SHAP values; regulatory compliance
False positive rate            Named as a concern          Quantified: 0.1% = 500K customers/day
Capacity                       Not quantified              6,000 TPS; 5ms inference; 40 Redis GETs
Retraining                     "Retrain periodically"      Weekly cadence; drift detection; shadow mode
```

---

## Pre-Interview Drill

```
Q: What is training-serving skew, and why does it matter for fraud?
A: Training-serving skew = features computed differently at training time vs. serving time.
   If training uses avg_30d computed over the full database but serving uses a pre-computed
   Redis value updated by Flink, they can diverge. Result: model performs worse in production
   than in offline evaluation. Fix: use the SAME feature computation code for training and serving.

Q: How do you handle the 30-90 day chargeback label latency?
A: Use multi-signal labels: manual review decisions (same day), card-stolen notifications
   from issuers (near-real-time), and user disputes (same day). Chargebacks are the ground
   truth but are combined with faster signals for more recent training data.

Q: A Redis velocity key stores all events in a ZSET (sliding window). Calculate the memory
   for 1M active cards with 100 events/hour average.
A: 1M cards × 100 events × 50 bytes = 5GB. Manageable in Redis with proper TTL.
   For high-cardinality dimensions (1B IP addresses), use Count-Min Sketch instead.

Q: How does graph-based fraud detection work, and why is it offline?
A: Build a graph of users, devices, cards, IPs. Run label propagation: confirmed fraud nodes
   spread fraud proximity scores to their neighbors. Offline (nightly Spark) because graph
   algorithms are expensive — label propagation on 1T edges takes hours. Score is stored in
   Redis as one feature in the online model.

Q: What's the difference between payment fraud, account takeover, and promo abuse?
A: Payment fraud: stolen card used for purchases. ATO: real user's account stolen. Promo abuse:
   fake accounts to claim bonuses. Different signals, different rules, often different models.
   Always clarify which type in an interview before designing the system.
```

---

## Common Interview Mistakes

**Mistake 1: Not quantifying the false positive cost.** Saying "minimize false positives" without
noting that at 0.1% FP rate on 500M transactions/day = 500K legitimate customers blocked per day.
This makes the engineering challenge concrete.

**Mistake 2: Designing only the ML layer.** Saying "build an ML model" without the rule engine
layer shows you haven't designed a production fraud system. Rules handle obvious cases faster
and more cheaply than ML.

**Mistake 3: Missing the feedback loop.** A fraud system without a feedback loop degrades over
time. Always describe how labels flow back to model retraining.

**Mistake 4: Using MySQL for velocity counters.** Querying MySQL for "how many transactions
in the last minute?" on every transaction is catastrophically slow at 6,000 TPS. Redis counters
are the only answer.

**Mistake 5: Forgetting training-serving skew.** Designing a feature store where training
queries Redshift and serving queries Redis, without guaranteeing they compute the same values,
shows unfamiliarity with ML engineering in production.

**Mistake 6: Missing explainability.** In regulated industries (finance, EU), automated
decisions must be explainable. Not mentioning SHAP or feature importance leaves a gap.

---

## Exercises

**Exercise 1:** Design the Redis data structure for a sliding window velocity counter that
tracks "number of transactions per card number in the last 60 seconds." Include the add,
count, and trim operations. Calculate the memory cost for 1M active card numbers with an
average of 3 transactions per minute.

**Exercise 2:** A new fraud attack is discovered: fraudsters are creating accounts using
real email domains but fake usernames, making purchases, and chargebacking immediately.
What new features and rules would you add? How would you detect this pattern in near-real-time?

**Exercise 3:** The fraud model's AUC-ROC has decreased from 0.97 to 0.91 over 3 months.
Diagnose the possible root causes and describe a systematic process to identify which one
is occurring.

**Exercise 4:** Design the schema for a graph fraud detection system. Define the node types,
edge types, and the label propagation algorithm. How would you store the resulting fraud
proximity scores for real-time serving?

---

## Homework

**Task 1:** Read Stripe Radar's documentation and blog posts on how their machine learning
fraud system works. Identify: (a) how they handle the false positive problem, (b) what their
stated fraud rates are, (c) how they allow merchants to customize rules.

**Task 2:** Implement a Count-Min Sketch in Python and test it against exact counting
for a Zipfian-distributed stream of IP addresses. Measure the error rate at different
sketch sizes (width × depth). What sketch size achieves < 1% error on the top-100 most
frequent IPs?

**Task 3:** Describe how you would A/B test a new fraud model without exposing your users
to additional fraud risk. What is the shadow mode strategy, and how do you measure success?

---

## KEY TAKEAWAYS

```
┌──────────────────────────────────────────────────────────────────────┐
│                    FRAUD DETECTION — KEY TAKEAWAYS                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ARCHITECTURE: LAYERED DEFENSE                                       │
│  Rules (< 1ms) → Velocity counters (5ms) → ML score (15ms) → Review │
│  Each layer handles what the previous layer can't.                   │
│                                                                      │
│  FALSE POSITIVES                                                     │
│  0.1% FP rate on 500M txns/day = 500K real customers blocked/day     │
│  Always quantify this. It's a first-class business metric.           │
│                                                                      │
│  VELOCITY COUNTERS                                                   │
│  Redis ZSET (exact sliding window) or fixed window with INCR/EXPIRE  │
│  ~40 velocity features; fetch in one Redis pipeline call → 5ms       │
│  Count-Min Sketch for high-cardinality (IP addresses)                │
│                                                                      │
│  FEATURE STORE                                                       │
│  Online: Redis (< 5ms); Offline: Spark batch (24h lag)               │
│  Training-serving skew is the #1 production ML failure mode          │
│  Fix: same feature computation code for training and serving         │
│                                                                      │
│  FEEDBACK LOOP                                                       │
│  Label latency: 30-90 days for chargebacks                           │
│  Mitigate: manual review labels (same day) + card-stolen signals     │
│  Retrain weekly; more often during active fraud campaigns            │
│                                                                      │
│  GRAPH FRAUD DETECTION                                               │
│  Build user/device/IP/card graph; run label propagation offline      │
│  Graph fraud proximity score → one feature in the online ML model    │
│  Detects fraud rings invisible to individual transaction scoring      │
│                                                                      │
│  LATENCY BUDGET                                                      │
│  21ms total: 1ms rules + 5ms velocity + 5ms features + 5ms model    │
│  Redis pipelining is essential (40+ GETs in one round trip)          │
│                                                                      │
│  KEY NUMBERS                                                         │
│  Stripe: ~6,000 TPS; 500M+ transactions/day                         │
│  Latency budget: < 200ms total; 21ms for fraud detection             │
│  Model features: 100–1000 per transaction                            │
│  Chargeback latency: 30-90 days                                      │
│  Retraining: weekly or more frequent during attacks                  │
│  Review SLA: 15 minutes for transactions > $10,000                   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Part 12: Operational Deep Dive — Incidents and Failure Modes

### Incident 1: Rule Misconfiguration Blocks 20% of Transactions

**What happened:** A fraud analyst deployed a new rule: "block if IP address country ≠
billing address country." Within 5 minutes, 20% of all transactions were being blocked
because many users are behind corporate VPNs or mobile carriers that geolocate to the
wrong country.

**Why it happened:** The rule was tested in shadow mode for only 2 hours on weekday traffic,
missing the pattern that weekend traffic has more VPN users. No kill switch was in place.

**Response timeline:**
```
T+0:   Rule deployed to production (100% traffic)
T+5m:  Alert fires: decline rate > 15% (normal: 2%)
T+6m:  On-call paged
T+8m:  On-call identifies the new rule via rule_decisions audit log
T+9m:  Rule disabled via emergency kill switch
T+10m: Decline rate returns to normal
T+30m: Post-incident analysis; rule revised to IP country ≠ billing country AND high-risk merchant
T+2h:  Revised rule deployed back to shadow mode for 7-day evaluation
```

**Prevention:**
1. Kill switch on every rule: disable in < 30 seconds without a deploy
2. Auto-kill switch: if any single rule fires on > 10% of traffic in 5 minutes, auto-disable
3. Gradual rollout: 1% → 5% → 25% → 100% of traffic, with a 30-minute soak at each stage
4. Shadow mode SLA: minimum 24 hours on representative traffic (include weekends)

### Incident 2: Model Degradation During Pandemic

**What happened (PayPal, March 2020):** COVID-19 lockdowns changed consumer spending patterns
dramatically overnight. Grocery and home goods transactions increased 300%; travel transactions
dropped 95%. The fraud model's AUC decreased from 0.97 to 0.88 within 2 weeks, and false
positive rate doubled.

**Root cause:** The model was trained on pre-pandemic data where "spending at grocery stores on
a weeknight" was unusual (higher fraud signal). During lockdowns, this became normal. The model
incorrectly flagged legitimate grocery purchases as suspicious.

**Response:**
1. Immediate: widen approval thresholds (accept higher false negative rate) to reduce false
   positive spike
2. Short-term: retrain model on last 30 days of data only (exclude pre-pandemic baseline)
3. Long-term: add recency weighting to training data; recent labels weighted 3x vs. older labels
4. Process change: implemented automated distribution drift monitoring; alerts when feature
   distribution shifts > 20% from rolling baseline

**Key lesson:** Fraud models must be continuously monitored for distribution drift. A one-time
validation against historical holdout data does not predict degradation during concept drift.

### Incident 3: Kafka Consumer Lag Causes Stale Features

**What happened:** A sudden 10x spike in transaction volume (Black Friday) caused the Kafka
consumer that updates online feature store (Redis) to fall behind by 2 hours. The fraud
model was scoring transactions using 2-hour-old velocity features.

**Result:** A fraud campaign that started at 9am (buying gift cards with stolen cards) went
undetected until 11am because the velocity features didn't reflect the spike. ~$500K in
fraud before the consumer caught up.

**Response:**
1. Scale up Kafka consumer group instances (horizontal scaling triggered by lag alert)
2. Alert threshold: Kafka consumer lag > 5 minutes → page on-call
3. Architecture change: velocity features served directly from Redis ZSET (updated synchronously
   in the request path via Redis pipeline), not from Kafka consumer. Kafka consumer only updates
   slower-changing features (user behavioral history, graph scores).

**Key lesson:** For velocity features that need < 1s freshness, update Redis synchronously in
the transaction request path, not via Kafka. Accept the 1-2ms overhead for freshness guarantees.

---

## Part 13: Device Fingerprinting and Account Takeover Detection

### Device Fingerprinting

Device fingerprinting creates a unique identifier for a device without requiring login or
cookies. It's critical for detecting fraud across multiple accounts (same device, different
accounts = suspicious).

```
FINGERPRINT COMPONENTS:
  Browser signals (web):
    - User agent string
    - Screen resolution, color depth
    - Installed fonts (Canvas fingerprinting)
    - WebGL renderer
    - Audio context properties
    - Timezone, language
    - Hardware concurrency (CPU cores)
    - Browser plugin list
    
  Mobile app signals:
    - Device model, OS version
    - Hardware identifiers (IDFV on iOS; Android ID)
    - Network interface MAC address (if available)
    - Battery status, charging state
    - Screen dimensions, DPI

FINGERPRINT STABILITY:
  Canvas + WebGL fingerprinting: stable across sessions but changes with major browser updates
  User agent + screen: changes more frequently
  
COMBINE SIGNALS:
  Hash all signals together → 64-bit fingerprint
  No single signal is reliable; the combination is.
  
FRAUD SIGNALS FROM FINGERPRINTS:
  Emulator detected: missing real hardware signals (all CPU cores identical, no battery variance)
  Known fraud device: this fingerprint appears in confirmed fraud transactions
  Device reuse across many accounts: fingerprint associated with 100+ different user accounts
  Headless browser: WebDriver flags, no real WebGL, no real audio context
```

### Account Takeover (ATO) Detection

ATO is different from payment fraud because the attacker has the real user's credentials.
The transaction looks legitimate from a "user identity" perspective.

```
ATO SIGNALS (unusual for a real user):
  Login from new device/country/IP (especially after a long gap in activity)
  Login followed by immediate high-value transaction (no browsing behavior)
  Password reset followed by new payment method addition
  Multiple failed logins before successful login (credential stuffing attempt)
  Shipping address changed to a new address immediately before purchase
  Transaction to a new payee immediately after login
  Device fingerprint ≠ any previous session for this account
  
ATO-SPECIFIC MODEL:
  Train a separate model just for ATO detection.
  Features: session behavior (mouse movements, typing speed, time-on-page),
            login event context (IP reputation, device familiarity, time since last login),
            post-login behavior sequence (how quickly actions were taken after login).
  This model runs on login events + early session activity, before the first transaction.

STEP-UP AUTHENTICATION:
  If ATO model score > threshold: require additional verification before allowing transactions.
  Options: SMS OTP, email OTP, security questions, push notification to trusted device.
  Friction is applied before the transaction, not after (which is too late).
```

### 5-Level Progression: ATO Detection

**Intern:** "Check if the login is from a new IP address. If yes, require OTP."

**Junior Engineer:** "New IP is too noisy — 30% of users travel and use VPNs. Better signal:
new device AND new IP AND new country simultaneously. Train a classifier on these signals."

**Mid-level Engineer:** "The ATO signal is in the SESSION BEHAVIOR, not just the login event.
A human logs in slowly, browses, then makes a purchase. A bot logs in immediately, changes
settings, makes a purchase — all within seconds. Behavioral biometrics (typing speed, mouse
movement patterns, time between actions) are hard for bots to fake and are a strong ATO signal."

**Senior Engineer:** "ATO detection must happen as early as possible in the session — at login,
not at payment time. Build a real-time session risk score that updates with each user action:
login event (initial risk), browsing behavior (lowers risk if it looks human), payment intent
(raises risk if velocity or amount is unusual). By the time the user hits 'pay,' you have
a rich session history. This session risk score feeds into the payment fraud model as a feature."

**Staff Engineer:** "ATO at scale requires a dedicated credential intelligence platform. You
want real-time access to: (1) Have I seen this email/password combination in a known credential
dump? (API integration with services like HaveIBeenPwned or internal intelligence). (2) Is
this IP in a botnet or credential stuffing attack right now? (Real-time IP reputation feed).
(3) Has this device been used to take over accounts before? (Device reputation from your own
historical data). None of these signals are in a standard ML feature set — they require
dedicated data partnerships and a credential intelligence service that your fraud team maintains.
The staff-level insight is that ATO defense requires cross-company data sharing (a credential
stolen from Company A gets used against Company B) and the best companies participate in
consortium threat intelligence sharing programs."

---

## Part 14: Regulatory Compliance

Fraud detection operates under strict regulatory constraints that affect system design.

### PCI DSS (Payment Card Industry Data Security Standard)

Any system that stores, processes, or transmits cardholder data (card number, CVV) must
comply with PCI DSS:

```
KEY PCI DSS REQUIREMENTS (relevant to fraud systems):
  Requirement 3: Protect stored cardholder data
    - Card numbers must be stored encrypted or tokenized (never plaintext in DB)
    - CVV must NEVER be stored after authorization (not even encrypted)
    - Fraud systems typically work with card tokens, not raw card numbers
    
  Requirement 6: Develop and maintain secure systems
    - Fraud scoring service must undergo regular penetration testing
    - Dependency scanning for known vulnerabilities
    
  Requirement 10: Track and monitor all access to cardholder data
    - All access to the transactions table must be logged
    - Log retention: 1 year minimum
    - Tamper-evident logs (write-once, append-only audit log)
    
  Requirement 12: Maintain an information security policy
    - Fraud analyst access to real transaction data requires approval and audit trail

TOKENIZATION:
  Real card: 4111111111111111 → Token: tok_abc123xyz
  The fraud system works with the token, not the real card number.
  Only the tokenization vault (separate, HSM-protected system) can reverse this.
  This limits PCI scope: most of the fraud system never touches real card numbers.
```

### GDPR / Data Minimization

In the EU, collecting and storing personal data for fraud detection must be justified
("legitimate interest" is the legal basis). Key requirements:

```
DATA MINIMIZATION:
  Only collect signals that are necessary for fraud detection.
  Don't collect behavioral biometrics for all users — only for high-risk sessions.
  
RIGHT TO EXPLANATION:
  Under GDPR Article 22, automated decisions that "significantly affect" users must
  be explainable. Fraud model decisions that decline a transaction qualify.
  Requirement: SHAP values or similar explanations must be stored and retrievable.
  
RIGHT TO DELETION:
  User requests account deletion → fraud data must be anonymized or deleted.
  Exception: data may be retained to comply with AML (Anti-Money Laundering) laws.
  Conflict: fraud detection benefits from historical data; GDPR limits retention.
  Resolution: anonymize after N years (replace user_id with random hash, keep
  fraud signal features for model training).
```

### AML (Anti-Money Laundering)

Financial institutions must detect and report transactions that may involve money laundering:

```
SUSPICIOUS ACTIVITY REPORTING (SAR):
  US Bank Secrecy Act: transactions > $10,000 cash must be reported (CTR).
  Structuring: splitting a large transaction into many small ones to avoid reporting = illegal.
  
FRAUD SYSTEM'S ROLE IN AML:
  The velocity checker that looks for "many small transactions" is ALSO an AML signal.
  "10 transactions of $990 in 2 hours" (structuring to avoid $10K threshold) = SAR required.
  
  ML model features for AML:
    - transactions_near_reporting_threshold (e.g., $9,900-$9,999)
    - transactions_structured_pattern (many transactions that sum to round number)
    - unusual_cross_border_transfers (inconsistent with account history)
    
AML vs. FRAUD:
  Fraud: protecting the payment platform and customers.
  AML: legal compliance with government regulations.
  They share infrastructure (velocity checks, ML) but have different decision thresholds.
  AML decisions (file a SAR) are made by a compliance team, not by automated systems.
  The fraud system surfaces signals; humans make the AML filing decision.
```

---

## Part 15: Stress Test Questions

**Q: "Your fraud model has a 0.1% false positive rate but you're now onboarding merchants
in high-risk countries with historically higher fraud rates. The false positive rate spikes
to 1% for those merchants. What do you do?"**

Correct approach: per-merchant, per-country thresholds. The global 0.1% FP target assumes
a certain fraud prevalence. Higher-risk environments warrant different thresholds.

- Short-term: raise the score threshold for high-risk merchants (accept more fraud to reduce FP)
- Medium-term: retrain the model with labeled data from high-risk countries (model doesn't
  know these patterns yet)
- Long-term: separate model per market segment (US consumer vs. LatAm B2B have very different
  fraud patterns)

**Q: "A competitor has just announced they are removing all fraud checks from their checkout
to reduce friction. Their conversion rate increased 2%. Your CEO asks: should we do the same?"**

This is an engineering judgment question about business trade-offs.

No, and here's why: fraud checks add 21ms to checkout latency, not the 200ms that could
meaningfully impact conversion. The 2% improvement likely comes from removing step-up
authentication (OTP requirements), not from removing fraud scoring. The correct response:
(1) A/B test: disable step-up auth for low-risk transactions only, measure conversion and
fraud impact. (2) Speed-optimize the fraud check to < 10ms to minimize any latency impact.
(3) Remember that increased fraud leads to increased chargebacks, which damage merchant
reputation with banks and can lead to higher interchange fees or account termination.

**Q: "A fraudster has discovered they can generate valid device fingerprints by spoofing
hardware signals in a virtual machine. Device fingerprinting stops working for detecting
reuse across accounts. How do you recover?"**

Device fingerprinting is one signal among many. When it degrades, other signals compensate:

- Shift weight to behavioral biometrics (harder to spoof: typing speed, mouse entropy)
- Increase weight on IP reputation and network signals
- Add graph-based signals: even if device fingerprint is spoofed, the IP/billing/email
  graph still reveals connections between fraud accounts
- Counter-measure: add harder-to-spoof signals: GPS coordinates (mobile), carrier information,
  SIM card age, phone number age
- Anti-fingerprint detection: if multiple "different" fingerprints share suspicious similarities
  (all have same screen resolution, same font list, slight variations) → flag as synthetic

**Q: "How do you test the fraud detection system before launching a new product (e.g., Stripe
launching a new Buy Now Pay Later product)?"**

Testing fraud detection for a new product type:

1. **Historical simulation**: take historical transactions from similar products (consumer
   installment loans), label them, and evaluate the model on this dataset. This reveals if
   the existing model transfers to the new product type.

2. **Rule review**: fraud analysts review the existing rule set for applicability. BNPL-specific
   patterns need new rules (e.g., "open multiple BNPL accounts within 30 days" is a fraud
   signal unique to BNPL).

3. **Shadow mode deployment**: run the model in shadow mode for the first 30 days — score
   all BNPL transactions but don't block any. Manually review transactions the model would
   have blocked. Are they actually fraud? This generates labeled data specific to the new
   product.

4. **Gradual ramp**: start with conservative thresholds (accept higher FP to minimize missed
   fraud). As labeled data accumulates, calibrate thresholds to the correct FP/FN balance.

5. **Feedback loop acceleration**: for a new product, actively recruit manual reviewers
   to label transactions quickly — don't wait 30-90 days for chargebacks. The faster you
   get labels, the faster the model learns the new product's fraud patterns.

---

## Part 16: SSE Brainstorming — More Fraud Scenarios

### Promo Abuse at Scale

**Scenario:** Your ride-sharing app offers $10 off the first 3 rides for new users.
Describe how fraudsters would abuse this and how you'd prevent it.

```
ATTACK VECTORS:
  1. Fake accounts: create 1000 Gmail addresses, use one per account
     Detection: email age (new Gmail created today), phone number age,
                device fingerprint reuse, IP velocity (1000 accounts from same IP)
  
  2. Device farms: physical devices with SIM rotation, genuine fingerprints
     Detection: GPS patterns (same location for all "different" users),
                behavioral similarity (all accounts use the app identically),
                payment method reuse (different accounts, same card)
  
  3. Referral manipulation: create fake referrals to harvest referral bonuses
     Detection: graph analysis (referrer and referee share device, IP, or billing),
                behavioral similarity between referrer and referee accounts

DEFENSES:
  - Require phone number verification with OTP (harder to automate at scale)
  - Limit promo to verified phone numbers only (no unverified email accounts)
  - Delay promo application: don't apply discount until 3rd ride (not 1st)
    → attacker must complete 2 rides to earn the 3rd ride discount; higher cost
  - Velocity limit: max 1 new account per device per week
  - Graph detection: cluster new accounts by device/IP/payment; block clusters

Uber's 2016 incident:
  $70M in fraudulent credits. Root cause: referral bonus was applied immediately,
  no verification required, and device/IP/payment graph was not checked.
  Fix: graph-based account clustering + delayed bonus application + phone verification.
```

### Chargeback Fraud (Friendly Fraud)

**Scenario:** A user legitimately purchases a $500 item, receives it, then files a chargeback
claiming they didn't authorize the transaction. This is "friendly fraud" — fraud against
the merchant by the buyer.

```
SCALE: ~30-40% of chargebacks are friendly fraud (not actual theft)
       At Stripe: potentially $100M/year+ in friendly fraud claims

DETECTION SIGNALS:
  - User has a history of chargebacks (high chargeback rate per account)
  - Transaction was delivered successfully (delivery confirmation from shipping provider)
  - Product was digital (no return possible): game keys, gift cards, subscriptions
  - User continued using the account after the "unauthorized" transaction
    (if truly unauthorized, typical behavior is to stop using the account)
  - Transaction matches user's typical pattern (same device, same address, same merchant category)

COUNTERMEASURE:
  Stripe's dispute evidence API: merchants submit evidence that the transaction was authorized.
  Fraud system tags transactions with "chargeback risk" score: high risk transactions get
  extra authentication (3DS), providing cryptographic proof of user authorization.
  3DS liability shift: if 3DS was used, the bank (not the merchant) is liable for the chargeback.
  This eliminates financial incentive for friendly fraud.
```

---

*This chapter pairs with:*
- *Ch58: Payment Flow — fraud scoring sits in the payment authorization path*
- *Ch104: Social Graph — graph-based fraud uses the same infrastructure*
- *Ch44: ML System Design — feature stores, model serving, feedback loops*
- *Ch25: Backpressure, Retries, Idempotency — fraud API must be idempotent*
- *Ch50: Rate Limiting — velocity checks are a specialized form of rate limiting*

*Chapter 105 — Section 6: Google/Meta System Design (Staff-Level Depth).*
*Core concepts: layered defense (rules → velocity → ML → review), feature store,*
*training-serving skew, label latency problem, graph fraud ring detection.*
*Key numbers: 6,000 TPS, 21ms latency budget, 30-90 day label latency, 0.1% FP target.*
---

## Part 17: System Architecture Diagram and Data Flow

```
COMPLETE FRAUD DETECTION SYSTEM ARCHITECTURE

CLIENT (mobile/web)
      |
      | POST /pay {card, amount, merchant, device_fingerprint}
      v
PAYMENT SERVICE (stateless HTTP handler)
      |
      |-- (1) Tokenize card → Card Vault (PCI-scoped system)
      |         Returns: card_token, bin
      |
      |-- (2) Enrich request: device fingerprint → Device Intelligence Service
      |         Returns: device_id, device_age, is_emulator, ip_reputation
      |
      |-- (3) POST /fraud/score → FRAUD SCORING SERVICE
      |         (< 200ms SLA)
      |
      v
FRAUD SCORING SERVICE
      |
      |-- [Layer 1] Rule Engine (< 1ms)
      |     - Blocklist lookups (known stolen cards, blocked IPs)
      |     - Hard velocity rules
      |     - Returns: BLOCK immediately OR proceed + rule_context
      |
      |-- [Layer 2] Redis Velocity Pipeline (5ms)
      |     PIPELINE [
      |       ZRANGEBYSCORE velocity:card:{token} {now-60s} {now}
      |       ZCARD velocity:card:{token}
      |       GET velocity:ip:{ip}:{minute_bucket}
      |       ... (40 velocity keys)
      |     ]
      |
      |-- [Layer 3] Online Feature Store Fetch (5ms)
      |     PIPELINE [
      |       HMGET user_features:{user_id} account_age fraud_rate avg_amount ...
      |       HMGET card_features:{card_token} bin_fraud_rate card_age ...
      |       GET graph_score:{user_id}  -- offline graph fraud score
      |     ]
      |
      |-- [Layer 4] Feature Engineering (3ms)
      |     - Compute derived features from raw signals
      |     - Combine velocity + user + transaction + device features
      |     - Output: 100-200 float features as array
      |
      |-- [Layer 5] ML Inference (5ms)
      |     - Serialize features → inference service
      |     - XGBoost predict_proba(features) → fraud_score
      |
      |-- [Layer 6] Decision Logic (2ms)
      |     - Apply per-merchant, per-amount thresholds
      |     - Map score → {APPROVE, STEP_UP_AUTH, REVIEW, BLOCK}
      |
      |-- [Async] Logging (fire-and-forget)
      |     - Write to Kafka topic: fraud_decisions
      |     - Consumed by: audit log, model training pipeline, review queue
      |
      v
Return {decision, fraud_score} to PAYMENT SERVICE
      |
      v
Payment Service: if APPROVE → send to card network (Visa/MC)
                 if BLOCK → return decline to client
                 if STEP_UP_AUTH → challenge client for OTP
                 if REVIEW → approve (optimistic) + enqueue for human review

ASYNC COMPONENTS (running continuously in background):

KAFKA STREAMS:
  fraud_decisions → model training pipeline (Flink)
  follow_events   → velocity feature updater (Flink → Redis)
  chargebacks     → label updater (annotates transactions table)

OFFLINE BATCH (nightly):
  MySQL transactions → Spark → graph analysis → fraud proximity scores → Redis
  labeled_transactions → model trainer → new XGBoost model → model registry
  
HUMAN REVIEW SERVICE:
  review_queue (MySQL) → reviewer UI → decision → 
  → feedback loop (label transaction) + → payment release/final decline
```

---

## Part 18: Capacity Planning

### Transaction Volume Estimates

```
STRIPE-SCALE CAPACITY:
  Volume:          ~500M transactions/day
  Peak TPS:        ~10,000 TPS (Black Friday spikes 5-10× average)
  Average TPS:     500M / 86,400 = ~5,800 TPS
  
  Fraud scoring service:
    CPU: 5,800 TPS × 21ms / 1,000ms = 122 cores minimum (with headroom: ~400 cores)
    Memory: inference model (50MB) × 400 pods = 20GB just for model artifacts
    
  Redis (velocity counters):
    Writes: 5,800 TPS × ~40 ZADD = 232,000 Redis ops/sec
    Reads:  5,800 TPS × ~40 GET  = 232,000 Redis ops/sec
    Total:  ~500,000 ops/sec
    Redis throughput limit: ~1M ops/sec per node (single-threaded)
    Required nodes: ~1 primary + 2 replicas per cluster; 3-5 Redis clusters
    Memory: 50 bytes × 100 events × 1M active cards = 5GB (manageable)
    
  Kafka:
    fraud_decisions topic: 5,800 messages/sec = ~2MB/sec (compact payloads)
    Retention: 7 days = 7 × 86,400 × 2MB = ~1.2TB per topic
    3 brokers sufficient for this throughput
    
  MySQL (review queue + transactions table):
    Insert rate: 5,800 rows/sec
    At 200 bytes/row: 5,800 × 200 = 1.16MB/sec ingestion
    Daily: 500M rows × 200 bytes = 100GB/day raw
    Partitioned by date; archive older than 90 days to S3
    
  Human review queue:
    ~0.7% of transactions need review (score 0.7-0.9)
    500M × 0.007 = 3.5M reviews/day
    At 3 minutes per review: 3.5M × 3min / 60min = 175,000 reviewer-hours/day
    That's ~7,300 full-time reviewers — WAY too many
    
REAL RESOLUTION: Auto-decline if review can't happen within SLA.
  For small amounts ($10 transactions in review for > 30min): auto-decline
  For large amounts ($10K+): maintain a smaller, dedicated high-value review team
  Most of the "review" bucket should actually be tightened thresholds so
  fewer transactions go to review — not more reviewers.
```

### Storage Estimates

```
TRANSACTIONS TABLE:
  500M rows/day × 365 = 182B rows/year
  Per row: ~200 bytes → 36TB/year
  With indexes: ~54TB/year
  Partitioned by month; older months on cheap S3 storage
  
FRAUD FEATURES TABLE (for model training):
  500M rows/day × 400 features × 4 bytes = 800GB/day → stored in S3 as Parquet
  Compressed (~4×): ~200GB/day in S3
  
VELOCITY COUNTERS (Redis):
  Active cards (transactions in last hour): ~5M
  5M × 100 events × 50 bytes = 25GB → fits on a single Redis instance
  With expiry (events outside 1-hour window auto-removed): stable size
  
REVIEW QUEUE (MySQL):
  ~3.5M new reviews/day
  Per review: ~500 bytes → 1.75GB/day
  Closed reviews purged after 90 days; archived to S3
  Active queue (pending + in-review): typically 100K-500K rows
  
MODEL ARTIFACTS (S3 + model registry):
  XGBoost model: ~50MB
  Previous 10 versions: 500MB
  Training datasets: 200GB/day × 365 = 73TB/year (Parquet, compressed)
```

---

## Part 19: Comparison — Stripe vs PayPal vs Uber Approach

```
COMPANY         STRIPE                  PAYPAL                  UBER
─────────────────────────────────────────────────────────────────────────────
Primary fraud   Card-not-present        Card-not-present,       Account fraud,
type            payment fraud           account takeover        promo abuse, driver fraud

Scale           ~500M txns/day          ~1.5B txns/day          ~25M rides/day

Primary model   XGBoost (Stripe Radar)  Ensemble (GBT + NN)     Multiple specialized models

Rule system     Stripe Radar DSL        Internal rules engine   Heuristics + ML hybrid

Graph analysis  Yes (cross-merchant     Yes (fraud rings,       Yes (referral graph
                card sharing)           synthetic identity)     fraud detection)

Feature store   Proprietary             Proprietary             Michelangelo (open-sourced)

Label source    Chargebacks +           Chargebacks + AML       Driver reports,
                dispute resolution      flags + manual          passenger reports,
                                        review                  route anomalies

Key innovation  Merchant-agnostic       3DS2 + liability        Trip anomaly detection
                scoring (works across   shift adoption          (route vs. GPS mismatch)
                all merchants equally)

PCI scope       Tokenization vault;     Full PCI Level 1        Cards handled by Braintree
                most system is          certified                (PayPal subsidiary)
                out-of-scope

Unique signal   Cross-merchant          PayPal balance          GPS telemetry
                velocity (same card     patterns (money         (trip route anomaly)
                at 10 merchants in 1h)  moving in/out)
```

---

## Part 20: Additional One-Liners and Quick Reference

```
DEFINITIONS:
  "Card testing" = small transaction to verify a stolen card works before making large purchases
  "Bust-out fraud" = build credit slowly over months, then withdraw all at once
  "Structuring" = splitting transactions to avoid reporting thresholds (AML violation)
  "Chargeback" = bank reversal of a transaction; merchant loses money + pays fee
  "Friendly fraud" = legitimate user claims they didn't authorize a transaction they did make
  "3DS" = 3D Secure; adds authentication step to card-not-present transactions; shifts liability
  "BIN" = Bank Identification Number; first 6 digits of card; identifies issuing bank + card type
  "SAR" = Suspicious Activity Report; filed with FinCEN (US) for suspected money laundering

KEY THRESHOLDS:
  Auto-approve:          score < 0.3
  Step-up auth (OTP):    score 0.3-0.5
  Human review:          score 0.5-0.7
  Hold for review:       score 0.7-0.9
  Auto-block:            score > 0.9
  (All thresholds are per-merchant, per-product, per-amount)

LATENCY BUDGET:
  Rules:                 1ms
  Velocity (Redis):      5ms (40 GETs pipelined)
  Feature store (Redis): 5ms (30 GETs pipelined)
  Feature engineering:   3ms
  ML inference:          5ms
  Decision + logging:    2ms
  TOTAL:                 21ms
  
COMPLIANCE ONE-LINERS:
  "Card numbers are tokenized; the fraud system never sees raw card numbers"
  "SHAP values satisfy the GDPR right to explanation for automated decisions"
  "AML structuring detection: flag transactions just below reporting thresholds in velocity"
  "Chargebacks are retained for 7 years even after account deletion (AML requirement)"
  "3DS liability shift: if used, issuing bank (not merchant) is liable for chargeback"
```

*This chapter pairs with:*
- *Ch58: Payment Flow — fraud scoring sits in the payment authorization path*
- *Ch104: Social Graph — graph-based fraud uses the same infrastructure*
- *Ch44: ML System Design — feature stores, model serving, feedback loops*
- *Ch25: Backpressure, Retries, Idempotency — fraud API must be idempotent*
- *Ch50: Rate Limiting — velocity checks are a specialized form of rate limiting*

*Chapter 105 — Section 6: Google/Meta System Design (Staff-Level Depth).*
*Core concepts: layered defense (rules → velocity → ML → review), feature store,*
*training-serving skew, label latency problem, graph fraud ring detection.*
*Key numbers: 6,000 TPS, 21ms latency budget, 30-90 day label latency, 0.1% FP target.*
*Incident patterns: rule misconfiguration kill switch, pandemic concept drift, Kafka lag.*
*Regulatory: PCI DSS tokenization, GDPR explainability (SHAP), AML structuring detection.*
---

## Part 21: How This Differs at Google

Google faces fraud across several surfaces: Google Ads (click fraud), Google Play (in-app
purchase fraud), Google Pay, and YouTube (fake engagement). The architecture is similar
but some design decisions differ.

### Click Fraud in Google Ads

Google Ads pays publishers per click. Fraudulent publishers use bots to click their own ads
and collect payments. Scale: Google Ads processes ~10B ad impressions/day; even 0.1% click
fraud = 10M fraudulent clicks/day.

```
CLICK FRAUD SIGNALS:
  - Click-through rate anomaly: publisher's CTR 10× higher than average
  - IP velocity: same IP clicking the same ad repeatedly
  - User agent patterns: headless browser, no JavaScript events
  - Behavior patterns: click within milliseconds of page load (human reads first)
  - Click-then-bounce: click, then immediately close tab (no engagement)
  - Geographic anomaly: ad shown in US, clicks from IP geolocating to Eastern Europe

KEY DIFFERENCE FROM PAYMENT FRAUD:
  Payment fraud: incorrect decision costs money immediately
  Click fraud: incorrect decision (charging advertiser for fake click) discovered in bulk,
               retroactively corrected via "invalid traffic" credits
  
  This allows a different architecture: clicks are logged first, scored offline,
  invalid clicks are filtered out before billing. Real-time blocking is only for
  the most obvious fraudsters (known bot IPs, impossible browser signatures).
  Less latency pressure: billing adjustments happen daily, not per-transaction.
```

### Synthetic Engagement on YouTube

YouTube counts views, likes, and watch time for ranking algorithms. Fake engagement
(view farms, like farms) distorts recommendations and can monetize fake popularity.

```
VIEW FRAUD SIGNALS:
  - IP reuse across accounts (watch farm: one IP with 1000 "users")
  - Watch pattern anomaly: every video watched exactly 30% (algorithm game to count as "view")
  - No pause/seek behavior (human viewers pause; bots watch straight through)
  - Geographic mismatch: video is in Polish, 80% of views from Brazil
  - Time-of-day clustering: all "views" happen in 3am-5am US time (non-US bot farm)
  
KEY SIMILARITY TO PAYMENT FRAUD:
  Graph analysis: accounts that watch the same set of videos in the same sequence form
  natural clusters (they're all watching the same "view farm" task queue)
  Label propagation: identify view farm clusters, penalize all accounts in cluster
```

### L6 Insight: Fraud as a Platform

At Google (and Facebook/Meta), fraud detection is a platform, not a per-product solution.
The same feature store, the same model serving infrastructure, the same rule engine, and
the same graph analysis pipeline are reused across Ads, Pay, Play, and YouTube. This is
the staff/L6 design insight: build reusable fraud primitives, not per-product fraud systems.

The platform investment pays off when a new product launches: instead of building fraud
detection from scratch, the new product team connects to the fraud platform, configures
product-specific rules, and starts collecting training data. Within weeks, a tuned model
is running rather than requiring months of infrastructure work.

```
FRAUD PLATFORM COMPONENTS:
  - Signal ingestion API (any product sends events)
  - Feature store with standard features (account age, velocity, device)
  - Model serving infrastructure (product teams bring their own model artifacts)
  - Rule engine with DSL (product teams write rules in same language)
  - Feedback loop SDK (product teams label outcomes, platform trains models)
  - Review queue with configurable SLAs (per-product routing rules)
  - Audit log + SHAP explainability service (compliance-ready)
```

---

## Part 22: Self-Check List Before the Interview

```
CONCEPTS TO EXPLAIN COLD (NO NOTES):

Layered defense:
  [ ] Can describe the 4 layers (rules → velocity → ML → review) and why each exists?
  [ ] Can give the latency budget (21ms) and how it breaks down?
  
Rule engine:
  [ ] Can give 5 real rule examples (not generic)?
  [ ] Can explain shadow mode, gradual rollout, and auto-kill-switch?
  
Velocity counters:
  [ ] Can write the Redis ZSET commands for a sliding window counter?
  [ ] Can explain fixed window vs. sliding window trade-off?
  [ ] Can explain why Count-Min Sketch is used for high-cardinality dimensions?
  
ML model:
  [ ] Can explain why XGBoost (not deep learning) is the default choice?
  [ ] Can name the 4-5 feature categories and 3 examples from each?
  [ ] Can define training-serving skew and explain how to prevent it?
  
Feature store:
  [ ] Can describe the online (Redis) + offline (Spark) split?
  [ ] Can explain what "point-in-time correct" features means?
  
Feedback loop:
  [ ] Can explain the 30-90 day chargeback label latency problem?
  [ ] Can name 3 faster label sources?
  
Graph fraud:
  [ ] Can describe the graph structure (node types, edge types)?
  [ ] Can explain label propagation at a high level?
  [ ] Can explain why graph analysis is offline, not real-time?

Regulatory:
  [ ] Can explain PCI DSS tokenization (why the fraud system never sees card numbers)?
  [ ] Can explain why SHAP values are needed for regulatory compliance?
  [ ] Can explain AML structuring detection (what signal are you looking for)?
```

*This chapter pairs with:*
- *Ch58: Payment Flow — fraud scoring sits in the payment authorization path*
- *Ch104: Social Graph — graph-based fraud uses the same infrastructure*
- *Ch44: ML System Design — feature stores, model serving, feedback loops*
- *Ch25: Backpressure, Retries, Idempotency — fraud API must be idempotent*
- *Ch50: Rate Limiting — velocity checks are a specialized form of rate limiting*

*Chapter 105 — Section 6: Google/Meta System Design (Staff-Level Depth).*
*Core concepts: layered defense (rules → velocity → ML → review), feature store,*
*training-serving skew, label latency problem, graph fraud ring detection.*
*Key numbers: 6,000 TPS, 21ms latency budget, 30-90 day label latency, 0.1% FP target.*
*Incident patterns: rule misconfiguration kill switch, pandemic concept drift, Kafka lag.*
*Regulatory: PCI DSS tokenization, GDPR explainability (SHAP), AML structuring detection.*
*Capacity: 500M txns/day → 400 cores, 25GB Redis velocity, 100GB/day MySQL, 200GB/day S3.*
---

## Part 23: Interview One-Liners

```
"Fraud detection = layered defense: rules → velocity → ML → human review."
"The false positive rate matters as much as the fraud rate — 0.1% FP on 500M txns = 500K real customers blocked/day."
"Velocity counters live in Redis — never query MySQL for 'transactions in last 60 seconds.'"
"Training-serving skew is the #1 failure mode in production ML: same code must compute features at both times."
"Label latency: chargebacks take 30-90 days — supplement with manual review and card-stolen signals."
"Graph fraud (fraud rings) is invisible to per-transaction scoring — requires offline graph analysis."
"PCI DSS tokenization: the fraud scoring service never sees raw card numbers."
"SHAP values satisfy GDPR's right to explanation for automated credit decisions."
"Rules are fast and interpretable; ML handles the ambiguous probabilistic middle ground."
"Shadow mode before any rule goes live: evaluate without acting, minimum 24 hours."
"Model drift: adversarial fraud shifts faster than your training data. Retrain weekly, or daily during attacks."
"Kill switch on every rule: misconfigured rules can block 20% of traffic in 5 minutes."
"Redis pipelining: send 40 velocity GET commands in one round trip → 5ms total vs. 40×1ms = 40ms."
"AML structuring: transactions clustered just below $10K reporting threshold are a regulatory signal."
"Chargeback liability shift: with 3D Secure, the issuing bank (not the merchant) is liable."
"Per-merchant thresholds: a $5 coffee shop tolerates more fraud than a $50K wire transfer."
"Promo abuse is account-level fraud: detect via device/IP/payment graph clustering."
"Fraud platform (not per-product): feature store + rule engine + model serving reused across all products."
"Review queue SLA: 15 minutes for high-value ($10K+), auto-decline if not reviewed in time for small amounts."
"Label propagation: fraud proximity score spreads 2 hops from confirmed fraud nodes in the transaction graph."
"Emulator detection: missing hardware variance (all CPUs identical, no battery state variation)."
"Velocity dimensions: card, BIN, account, device, IP, email — each with 1min/1hr/1day/7day windows."
"XGBoost over neural nets for fraud: interpretable, fast inference (5ms), no GPU required."
"Point-in-time correct: training features must use only information available at the transaction's timestamp."
"Model rollback SLA: < 5 minutes to revert to previous version if new model causes false positive spike."
"Gradual rule rollout: 1% → 5% → 25% → 100% with 30-minute soak at each stage."
"Behavioral biometrics: typing speed, mouse entropy, time-between-actions — hard for bots to fake."
"Synthetic identity fraud: builds credit slowly over months using real SSN + fake name, then 'busts out.'"
"Friendly fraud: legitimate user claims unauthorized charge for item they received. ~30-40% of all chargebacks."
```

*This chapter pairs with:*
- *Ch58: Payment Flow — fraud scoring sits in the payment authorization path*
- *Ch104: Social Graph — graph-based fraud uses the same infrastructure*
- *Ch44: ML System Design — feature stores, model serving, feedback loops*
- *Ch25: Backpressure, Retries, Idempotency — fraud API must be idempotent*
- *Ch50: Rate Limiting — velocity checks are a specialized form of rate limiting*

*Chapter 105 — Section 6: Google/Meta System Design (Staff-Level Depth).*
*Core concepts: layered defense (rules → velocity → ML → review), feature store,*
*training-serving skew, label latency problem, graph fraud ring detection.*
*Key numbers: 6,000 TPS, 21ms latency budget, 30-90 day label latency, 0.1% FP target.*
*Incident patterns: rule misconfiguration kill switch, pandemic concept drift, Kafka lag.*
*Regulatory: PCI DSS tokenization, GDPR explainability (SHAP), AML structuring detection.*
*Capacity: 500M txns/day → 400 cores, 25GB Redis velocity, 100GB/day MySQL, 200GB/day S3.*
*Google-specific: click fraud (retroactive billing correction), view farm detection, fraud platform.*
*Promo abuse: phone verification + delayed bonus + graph clustering prevent referral fraud.*
*Friendly fraud (30-40% of chargebacks): 3DS liability shift + delivery confirmation evidence.*
*ATO detection: session behavioral biometrics + credential intelligence platform + step-up auth.*
*Model retraining trigger: weekly by default; daily if fraud rate rises > 20% above rolling baseline.*
*Auto-kill switch threshold: any rule firing on > 10% of traffic in 5 minutes → auto-disabled + paged.*
*Feature categories: transaction (no lookup), velocity (Redis), user/card/device (online store), graph (offline).*
*Redis pipeline is not optional: 40 GETs pipelined = 5ms; 40 sequential GETs = 40ms = latency budget blown.*
*Card tokenization: fraud system uses card_token (not raw PAN); only vault can reverse; limits PCI scope.*
*Feedback sources ranked by speed: card-stolen signal (hours), manual review (minutes), chargeback (months).*
*Review queue design: SLA by amount tier; auto-decline if SLA expires for low-value transactions.*
*Community detection algorithms for fraud rings: Louvain (fast, greedy) and label propagation (iterative).*
*Behavioral biometrics as ATO signal: mouse entropy, keystroke timing, session action sequence modeling.*
*BIN (Bank Identification Number): first 6 digits of card. High-risk BINs (high-chargeback issuers) flag.*
*3DS (3D Secure): cardholder authenticated by their bank; shifts liability to issuing bank on fraud.*
*Training dataset size: 6 months of labeled transactions = ~90B rows for Stripe; Parquet + Spark needed.*
*Model inference hardware: XGBoost on CPU (not GPU); 5ms for 100 features on a single core.*
*Drift detection methods: KL divergence for distribution shift, AUC monitoring for performance drift.*
*Promo abuse defense: require phone OTP + delay bonus application + device/IP graph deduplication.*
*Kafka consumer lag on Black Friday: velocity features went 2 hours stale → fix: update Redis synchronously.*
*Regulatory audit trail: store rule_decisions + model_predictions + SHAP values per transaction for 7 years.*
*Threshold calibration by merchant type: low-risk merchant (coffee shop) has higher fraud tolerance than.*
*  high-risk merchant (gift cards, crypto exchange) — thresholds tuned per merchant category code (MCC).*
*Model A/B test: split traffic 90/10; measure fraud rate + FP rate + revenue impact on 10% cohort.*
*Feature importance top-3 in most fraud models: device_age, velocity_1min_per_card, ip_reputation_score.*
*Score distribution: most transactions score < 0.1; a small tail scores > 0.7; the 0.3-0.7 range is key.*
*Real-time vs. offline feature latency: same feature, different freshness: Redis (< 1s) vs. Spark (24h).*
*Friendly fraud mitigation: 3DS removes financial incentive (liability shifts); delivery proof for disputes.*
*Chapter 105 covers the complete fraud detection lifecycle from ingestion through labeling and retraining.*
*Pairs well with Ch44 (ML System Design) for model serving patterns and Ch58 (Payment Flow) for context.*
*Fraud types in priority order: payment fraud (most common), ATO, promo abuse, synthetic identity.*
*Rule performance metrics: hit rate (% of transactions triggering rule), precision (fraud among triggered).*
*False positive cost is often larger than fraud cost — never optimize for recall alone in fraud systems.*
*At Google scale: fraud is a platform, not a per-product system; feature store + rule engine are shared.*
*Key insight: the adversarial nature makes fraud detection a continuous arms race, not a shipped feature.*
*Systems design framing: fraud = streaming ML + feature store + rule engine + feedback loop + graph analysis.*
*Minimum viable system: rules → Redis velocity → XGBoost model. Advanced: graph + explainability + platform.*
*L5 interview: describe the layers and why each exists. L6: quantify latency, explain training-serving skew.*
*Production alert thresholds: fraud rate > 0.2%, FP rate > 0.2%, model AUC < 0.93, Kafka lag > 5min.*
*Fraud budget allocation: ~40% engineering on feature store + feedback loop, ~30% model, ~30% rules + ops.*
*Regulatory recap: PCI = tokenize cards; GDPR = explain decisions (SHAP); AML = detect structuring; SAR filing.*
*Chargeback fee: $25-50 per dispute + merchandise loss; 1% chargeback rate = account termination risk.*
*Card network rules: Visa/MC require chargeback rate < 1% (warning at 0.65%); non-compliance = fines.*
*Fraud monitoring dashboards: real-time fraud rate, FP rate by merchant, model score distribution histogram.*
*Shadow mode is non-negotiable: never deploy a new rule or model directly to 100% production traffic.*
*Last updated: 2026-06-25. System Design for L6: The Complete Guide.*

---

## Interview Simulation — Fraud Detection (Stripe / PayPal) (Staff / L6)

*45-minute Staff-level system design interview. Phases follow the Section 2 framework.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design the fraud detection system for a payment platform at Stripe scale. Where do you start?

**Candidate:** A few questions. First — what types of fraud are we targeting: card-not-present fraud (stolen card used online), account takeover, chargeback fraud (friendly fraud), or all three? Each has different feature sets. Second — what's the latency budget? For a payment authorization, we're inside a < 300 ms total window — how much can fraud detection use? Third — what's the current fraud rate baseline, and what's the acceptable false positive rate? Blocking a legitimate transaction is costly (customer friction, potential churn). Fourth — do we need to be explainable — can we give a reason for a decline, or is a black-box ML model acceptable?

> **Interviewer:** All three fraud types. Latency budget: < 50 ms for fraud decision. False positive rate < 0.2% (premium users expect near-zero friction). Explainability required for regulatory compliance (GDPR Article 22).

**Candidate:** Functional requirements: (1) Real-time fraud scoring for every transaction within 50 ms. (2) Velocity checks: rate of transactions per user, card, IP, device. (3) Two-stage pipeline: rule engine for obvious fraud, ML model for nuanced patterns. (4) Chargeback feedback loop to retrain models. (5) Shadow mode deployment for new models. Non-functional: < 50 ms p99 for fraud decision, 99.99% availability (downtime = revenue loss), < 0.2% false positive rate, model decisions explainable via SHAP values.

---

### Phase 2: Estimation (4 min)

**Candidate:** Stripe processes ~1 billion transactions per day → ~11,500 transactions/s average, ~50,000 transactions/s peak. Each transaction triggers one fraud evaluation. Feature store lookups: each evaluation reads ~40 features — user velocity (last 1h, 24h), device fingerprint history, merchant category, card BIN risk score, geographic anomaly score. Each feature lookup is a Redis read: 40 lookups × 11,500/s = 460,000 Redis reads/s. At 100K ops/s per Redis node, we need ~5 nodes (plus replicas). ML model inference: a 1,000-tree XGBoost model on 40 features takes ~2 ms on CPU. At 50,000 transactions/s, we need ~100 CPU cores dedicated to inference. Model storage: 1,000 trees × ~10 KB per tree = 10 MB per model — loads entirely in L3 cache, very fast inference.

---

### Phase 3: API Design (4 min)

**Candidate:** Internal API only — fraud detection is not exposed externally. `POST /v1/fraud/evaluate` body `{transaction_id, user_id, card_token, amount, merchant_id, device_fingerprint, ip_address, billing_address}` returns `{fraud_score: 0.0-1.0, decision: ALLOW/REVIEW/BLOCK, rule_triggers: [...], shap_values: {...}, evaluation_id}`. The response includes both the decision and the explainability artifacts (SHAP values and which rules triggered) — needed for regulatory compliance and for the customer service team to explain a decline. `POST /v1/fraud/feedback` body `{transaction_id, outcome: CHARGEBACK|LEGITIMATE|MANUAL_REVIEW_APPROVED}` — triggers the feedback loop. `GET /v1/fraud/velocity/{user_id}?window=1h` — internal query for the customer service dashboard.

> **Interviewer:** Why return SHAP values in the real-time response rather than computing them asynchronously?

**Candidate:** GDPR Article 22 requires that automated decision-making be explainable to the affected person on request. If a customer calls to dispute a declined transaction, the support team needs the explanation immediately — not after an async job runs. We precompute SHAP values inline because XGBoost TreeSHAP runs in O(T×D) where T is number of trees and D is tree depth — for our 1,000-tree model, this adds ~1 ms to inference time. Acceptable given the 50 ms budget. The alternative (async SHAP computation stored in a database) creates a race condition if the customer calls before the async job completes.

---

### Phase 4: Data Model (4 min)

**Candidate:** Three stores. Feature store (Redis): `velocity:{user_id}:1h` → sorted set of transaction timestamps (ZRANGEBYSCORE with time window gives count), `velocity:{card_token}:24h` → same pattern, `device:{fingerprint}:risk_score` → float. Keys have TTL matching their window size + 10%. Each transaction writes to these keys atomically in a pipeline. Transaction log (Kafka + Iceberg on S3): every evaluation result stored with all features and model output. Schema: `{transaction_id, timestamp, user_id, features_json, fraud_score, decision, rule_triggers, shap_values_json, final_outcome (updated via feedback)}`. This is the training dataset for the next model version. Chargeback table (PostgreSQL): `{transaction_id, chargeback_filed_at, amount, dispute_reason, outcome}`. Joined with the Iceberg transaction log to compute model performance metrics and generate training labels.

---

### Phase 5: HLD + Deep Dive (20 min)

**Candidate:** The two-stage pipeline:

```
TRANSACTION FRAUD EVALUATION (< 50ms)
======================================

Payment Service
  │ transaction arrives
  ▼
Fraud Gateway (synchronous, on payment auth critical path)
  │
  ├─1► Feature Fetch (Redis, parallel, 5ms)
  │       user velocity (1h, 24h, 7d)
  │       card velocity (1h, 24h)
  │       device fingerprint risk score
  │       IP reputation (Spamhaus + internal)
  │       merchant category risk
  │       billing/shipping address mismatch flag
  │       → 40 features total, all from Redis
  │
  ├─2► Rule Engine (in-process, 2ms)
  │       Rules (examples):
  │       - card used in 3+ countries in 1 hour → BLOCK
  │       - transaction amount > 10× user's 30-day avg → REVIEW
  │       - device fingerprint seen on 5+ accounts → BLOCK
  │       - merchant in high-risk MCC + card < 7 days old → REVIEW
  │       → if any BLOCK rule: short-circuit, skip ML
  │       → if any REVIEW rule: ML runs but score thresholds lower
  │
  ├─3► ML Inference (XGBoost, CPU, 3ms)
  │       40 features → fraud_score [0.0, 1.0]
  │       TreeSHAP → shap_values per feature
  │       decision thresholds:
  │         score < 0.3 → ALLOW
  │         0.3-0.7 → REVIEW (manual review queue)
  │         score > 0.7 → BLOCK
  │
  ├─4► Decision + Response Assembly (1ms)
  │       merge rule triggers + ML decision
  │       write to Kafka (async, non-blocking on response path)
  │       update velocity counters in Redis (async pipeline)
  │
  └─► Return {fraud_score, decision, rule_triggers, shap_values}
      to Payment Service (total: ~11ms, well within 50ms budget)

FEEDBACK + RETRAINING LOOP
============================
Chargeback events
  │ (filed 30-90 days after transaction)
  ▼
Chargeback Processor
  │ joins with Iceberg transaction log on transaction_id
  │ labels transaction as FRAUD
  │
  ▼
Training Pipeline (weekly)
  │ pull 90-day window from Iceberg
  │ feature engineering (same as production features)
  │ train XGBoost on fraud/legitimate labels
  │ evaluate: AUC, precision at 0.2% FP rate
  │
  ├─► Shadow Mode: new model runs in parallel (SHADOW flag)
  │       predictions logged but NOT used for decisions
  │       compare shadow predictions to production outcomes
  │       A/B test: does shadow model improve AUC?
  │
  └─► Canary Deploy (if shadow AUC > production AUC + 0.5%):
          route 1% of traffic to new model
          monitor fraud rate + FP rate in real time
          gradual rollout: 1% → 5% → 20% → 100%

VELOCITY COUNTER ARCHITECTURE
===============================
Redis Sorted Set per velocity dimension:
  Key: vel:{user_id}:{window}
  Value: ZADD with score=timestamp, member=transaction_id
  Query: ZCOUNT vel:{user_id}:1h (now-3600) now
  Write: ZADD + EXPIRE (async, after response returned)

Pros: exact counts, O(log N) write and read
Cons: memory proportional to transaction count per window
Scale: 50K TPS × 3600s = 180M members per user-hour key
  → impractical for high-velocity users
Solution: sliding window approximation using two fixed
  buckets (current + previous 1h), weighted average:
  approx_count = count(current_bucket) +
    count(prev_bucket) × (1 - elapsed_fraction)
  Memory: 2 counters per dimension vs O(TPS×window) members
```

**Deep Dive 1: Rule Engine + ML Two-Stage Architecture.**

The rule engine handles the obvious cases at near-zero cost: a card used in three countries in one hour is fraud — no ML needed. Rules are fast (2 ms), fully explainable (the rule that triggered is the explanation), and easily maintained by the fraud operations team without engineering involvement. Rules are stored in a YAML config file, hot-reloaded without deployment, and versioned in Git for audit. The ML model handles the gray zone: a transaction that looks slightly unusual but doesn't trigger any rule. The model captures complex feature interactions (a $200 transaction is suspicious for a user who always spends < $50, but not for a user who spends $500/day) that would require exponentially many rules to capture explicitly. The two-stage architecture is also a latency optimization: ~30% of transactions are blocked by rules without reaching the ML model, saving inference compute.

> **Interviewer:** How do you handle training-serving skew — features computed differently at training time vs inference time?

**Candidate:** *(Cross-question: training-serving skew)* This is the most common failure mode in production ML. Training-serving skew happens when training computes features from the offline transaction log differently from how the production feature store computes them. Two defenses. First, use the same feature computation code for both: the feature store's Redis population logic is the same Python function as the training pipeline's feature engineering. We enforce this via a shared library — the features module is imported in both the production service and the Spark training job. Changes to the library require updating both and running a drift test. Second, log all features at inference time in the Iceberg transaction log. Training uses these logged features (not recomputed from raw data), which are guaranteed to match what the model saw in production. The exception: for the first model training, we must use historically computed features — we document this as the "cold start skew window" and accept that the first model version has slightly degraded performance.

**Deep Dive 2: Shadow Mode Deployment.**

The rule: never deploy a new fraud model or rule directly to 100% production traffic. A new model that increases the fraud block rate from 0.5% to 1.0% might be catching more fraud — or might be over-blocking legitimate transactions. Shadow mode separates these. The new model runs in parallel with the production model: it receives the same transaction data and produces a fraud_score, but the score is logged and NOT used for the decision. We compare shadow scores against production outcomes over 2 weeks: if transactions the shadow model flagged (score > 0.7) but the production model allowed subsequently result in chargebacks at a higher rate, the shadow model is better. If they chargeback at the same rate as production-allowed transactions, the shadow model is over-triggering. Canary deploy follows shadow validation: 1% of traffic, real decisions, monitor FP rate hourly. A FP rate spike at canary stage stops the rollout automatically.

> **Interviewer:** How do you handle velocity checks for a business that legitimately processes thousands of transactions per hour?

**Candidate:** *(Cross-question: high-velocity legitimate accounts)* Merchant context is a feature, not an override. A business account (merchant_type = B2B_PLATFORM) processes 10,000 transactions/hour legitimately. The velocity feature for this account should not trigger fraud rules. We handle this by segmenting velocity thresholds by account tier: consumer accounts use tight velocity limits (50 transactions/day), marketplace accounts use looser limits (1,000/day), and enterprise accounts have custom velocity profiles (stored in account metadata, fetched as part of the feature set). The ML model also learns these patterns: a high-velocity account that has processed transactions consistently for 2 years with zero chargebacks has very different feature distributions than a newly created high-velocity account.

---

### Common Cross-Questions and Strong Answers (Staff Level)

**Q: How do you handle the cold start problem — a brand new user with no history?**
A: New users have no velocity features, no device history, no behavioral baseline. We use four signals. First, device fingerprint: if the device has been seen before (even on a different account), we inherit the risk score of that device's prior activity. Second, email domain risk: disposable email addresses (mailinator.com, guerrillamail.com) are high-risk signals for new accounts. Third, card BIN data: the first 6-8 digits of a card number identify the issuing bank and card type — a prepaid virtual card from a high-risk country is a stronger signal than a Visa credit card from Chase. Fourth, behavioral biometrics during signup: typing speed, mouse movement patterns, and form fill speed are distinct for bots vs humans. New user risk scores are therefore higher than established users, and thresholds are adjusted — we accept slightly higher FP rates for new users until they build history.

**Q: A new fraud pattern emerges that your model and rules have never seen. How do you detect it?**
A: Monitoring for distribution shift. We run daily checks on feature distributions: if the mean transaction amount for a user segment shifts by > 2σ from its 30-day baseline, that's an anomaly. We also monitor model confidence calibration: if the model is suddenly making many predictions in the 0.4–0.6 range (uncertain territory) for a class of transactions it previously scored confidently, the underlying data distribution has changed. Operational signal: a spike in chargebacks 30–60 days after a new fraud pattern starts is the lagging indicator. We address this with a rapid response loop: fraud operations analysts can create new rules within hours (YAML config, no engineering required), providing coverage while the model retrains on the new pattern.

**Q: How do you prevent internal fraud — an employee with database access modifying fraud scores?**
A: Defense in depth. First, the fraud score is written to Kafka as an immutable event — appending, never updating. Any modification requires deleting and re-creating an event, which is logged. Second, the fraud evaluation service runs with a service account that has write-only access to Kafka and read-only access to the feature store — it cannot read or modify past decisions. Third, the Iceberg transaction log on S3 uses S3 Object Lock (WORM compliance) — files cannot be deleted or modified for a configurable retention period. Fourth, all model deployment actions require a two-person approval in the CI/CD pipeline. Fifth, we run a quarterly audit: randomly sample 1,000 ALLOW decisions and verify they match the model's documented prediction for those features — any discrepancy is investigated.

*Shadow mode is non-negotiable: never deploy a new rule or model directly to 100% production traffic.*
*Last updated: 2026-06-25. System Design for L6: The Complete Guide.*
