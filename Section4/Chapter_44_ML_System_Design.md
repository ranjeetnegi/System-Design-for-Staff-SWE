# Chapter 41a: ML System Design

> **Core Thesis:** ML system design is not about the model. It is about the plumbing that feeds
> the model, serves its predictions, and keeps it honest over time. Most engineers get hired to
> build that plumbing, not to invent the model. This chapter teaches you to design that plumbing.

---

## Part 0: Why This Chapter Matters for Your Interview

### Which Interview Questions This Chapter Answers

This chapter prepares you to answer the following types of L6 interview questions — all of which
appear regularly at Google, Meta, Amazon, and similar companies:

- "Design a recommendation system for YouTube / Netflix / Spotify."
- "Design a real-time fraud detection system for a payment processor."
- "Design the search ranking system for a major e-commerce site."
- "Design the ad targeting / CTR prediction system for a social media platform."
- "Design the feed ranking system for a social network."
- "You have a model in production. Three weeks after deployment, accuracy has dropped 30%.
  How do you diagnose and fix it?"

These questions are not asking you to be an ML researcher. They are asking you to be a
**systems engineer who understands ML pipelines**. The candidate who talks about transformer
architectures and loss functions for 30 minutes fails. The candidate who talks about feature
freshness, training-serving skew, monitoring, and rollback strategy for 30 minutes passes.

### The Mental Model Shift

Here is the single most important thing to understand before reading this chapter:

**ML system design is not about the model — it is about the plumbing.**

Every software engineer already knows how to design plumbing: databases, caches, queues, APIs,
monitoring. An ML system adds one new component — the model — and wraps the same plumbing
concepts around it. The model takes features as input and produces a prediction as output.
Treat it like a function call: `model.predict(features) → score`.

Your job is to design:
1. How the features get computed correctly (feature pipeline)
2. How the features get to the model at the right time and with the right freshness
3. How the model's predictions get to the user reliably and quickly
4. How you detect when the model has gone wrong
5. How you safely update the model without breaking production

That is it. Five concerns. Every ML interview question at L6 is really about these five concerns.

### The 5-Second Summary for Non-ML Engineers

If you are an infrastructure engineer who has never worked on ML, here is everything you need
to know before your interview:

```
THE ML SYSTEM IN ONE PARAGRAPH

An ML model is like a vending machine: you put in coins (features = input data) and it
gives you a snack (prediction = output). Your job as an ML systems engineer:

1. Make sure the right coins are always in stock (feature pipeline — data freshness)
2. Make sure the coin slot accepts your coins without jamming (training-serving skew)
3. Make sure the vending machine is fast enough (serving latency)
4. Make sure the vending machine is giving out fresh snacks, not expired ones (model drift)
5. Make sure you can swap in a new vending machine without anyone noticing (deployment)

The vending machine itself (the model) is not your problem. The vending machine company
built it. You built the building it sits in, the power supply, and the inventory system.
```

### How L6 Differs From L5 on ML System Design

The clearest single difference: **L5 engineers think about the happy path. L6 engineers think
about the failure modes.**

An L5 candidate designs an ML system that works when:
- All features arrive on time
- The model produces valid predictions
- The feedback loop behaves as expected
- The training data is clean

An L6 candidate designs the same system AND addresses what happens when:
- The feature pipeline is 3 hours late (stale features → degraded predictions)
- The model produces null or out-of-range predictions (fallback logic)
- The feedback loop teaches the model the wrong thing (exploration policy, label auditing)
- The training data has label noise or selection bias (data validation gates)

Demonstrating L6 thinking in the interview means **you proactively raise the failure modes**
without being asked. You do not wait for the interviewer to say "what happens if X fails?"
You say it yourself: "I want to flag a risk here — the feedback loop can cause filter bubbles
if we do not add an exploration budget. Let me address that before we move on."

---

## Who This Chapter Is For

You know distributed systems. You have built APIs, caches, queues, databases. You can design a
ride-sharing backend or a URL shortener. But when the interviewer says "design a recommendation
system" or "build a fraud detection system," you go blank — because there is an ML model in the
middle and you are not sure how to treat it.

Here is the reframe: **treat the ML model like a database query.** It takes inputs (features),
returns an output (prediction), and your job is to make sure the right data flows in and the
output flows out reliably and quickly. That is it. You do not need to understand backpropagation
to design an ML system. You need to understand pipelines, latency, staleness, and failure modes.

---

## Part 1: Why ML System Design is Different

### The Determinism Gap

Think about a traditional system. You call `getUserById(123)`. Every single time, you get the
same user record (assuming the data has not changed). The system is **deterministic**: same
input, same output. You can test it, cache it, and reason about it reliably.

Now think about an ML system. You call `predictChurnProbability(user_id=123)`. Today it returns
0.72. Next week it returns 0.43. The user has not changed. But the **model** has been retrained
on new data, and the world has changed. This is **probabilistic and temporal**: the same input
can produce different outputs over time.

This difference causes most ML production failures. Engineers who are used to deterministic
systems do not expect their "database query" to silently change behavior after a deployment.

```
TRADITIONAL SYSTEM

Input ──────────────────────────────────▶ Output
  "get user 123"                           { name: "Alice", age: 30 }
  
  Same input tomorrow? Same output. ✓


ML SYSTEM

Input ──────────────────────────────────▶ Output
  "predict churn for user 123"             0.72  (today, model v1)
  
  Same input next week?
  
Input ──────────────────────────────────▶ Output
  "predict churn for user 123"             0.43  (next week, model v2)
  
  The model changed. The world changed. Output changed. 
  Was that expected? Did anyone notice? ← THIS is the problem.
```

### The Two-Phase Problem

Every ML system has two completely different modes of operation that must coexist:

**Training Phase (offline, batch):** You take historical data — billions of rows — and use it to
teach the model what good predictions look like. This happens on a schedule (daily, weekly) or
when triggered. It is slow. It is expensive. It is run on a cluster. It produces a model file.

**Serving Phase (online, real-time):** A live user does something — clicks a search result, makes
a payment — and within 100ms you must return a prediction. You load the model, compute features,
run inference. It is fast. It is cheap per call. It is run on a server.

The problem: these two phases run on different infrastructure, at different times, with different
data pipelines. Keeping them consistent is the core challenge of ML engineering.

```
TRAINING PHASE (offline)                 SERVING PHASE (online)

Runs: nightly/weekly                     Runs: every user request
Data: historical (terabytes)             Data: real-time (single row)
Speed: hours to complete                 Speed: <100ms to respond
Output: model file                       Output: prediction
Where: GPU cluster / Spark               Where: prediction server

     ┌──────────────┐                         ┌──────────────┐
     │ 6 months of  │                         │  Live user   │
     │  user data   │                         │   request    │
     └──────┬───────┘                         └──────┬───────┘
            │                                        │
            ▼                                        ▼
     ┌──────────────┐                         ┌──────────────┐
     │   Feature    │ ◀── MUST MATCH ────────▶│   Feature    │
     │   Pipeline   │   (skew = bug)          │   Pipeline   │
     └──────┬───────┘                         └──────┬───────┘
            │                                        │
            ▼                                        ▼
     ┌──────────────┐     model file          ┌──────────────┐
     │   Training   │ ──────────────────────▶ │   Model      │
     │   Job        │                         │   Server     │
     └──────────────┘                         └──────────────┘
```

### The Four Hard Problems

1. **Data Freshness:** How old can the training data be before the model gets stale? A fraud
   model trained on last month's data may miss new fraud patterns that emerged this week.

2. **Training-Serving Skew:** The feature pipeline in training computes features one way. The
   feature pipeline in serving computes them slightly differently (different code, different
   timezone handling, different NULL treatment). The model was trained on features computed one
   way and is served on features computed another way. Accuracy silently degrades.

3. **Feedback Loops:** The model makes predictions. Those predictions change user behavior. That
   behavior becomes new training data. The next model is trained on behavior that the previous
   model caused. You are no longer training on ground truth — you are training on your own
   history.

4. **Model Drift:** The world changes. Fraud patterns change. User preferences shift. A COVID
   pandemic happens. The relationship between your features and the correct label changes over
   time. The model quietly gets worse, and no one notices until business metrics tank.

### Intern → Staff Progression (Part 1)

| Level | How they think about ML system design |
|-------|---------------------------------------|
| **Intern** | "We train a model and deploy it." Thinks of it as a one-time task. |
| **L3** | Knows about training and serving as separate phases. Wires them together manually per project. |
| **L4** | Recognizes training-serving skew as a risk. Starts thinking about shared feature pipelines. |
| **L5** | Builds a reusable training pipeline. Adds basic model monitoring. Thinks about retraining schedules. |
| **L6** | Designs the full system: unified feature store (eliminating skew), drift detection, automatic retraining triggers, A/B testing infrastructure, feedback loop correction. Treats each component as a failure domain. |

---

## Part 2: The Full ML System Architecture

Before going deep on any component, here is the full picture. Every ML system at scale has these
parts. The differences between companies are in how they implement each box, not whether the
box exists.

```
                         FULL ML SYSTEM ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

  DATA SOURCES
  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │ User Events │  │  Databases  │  │  3rd Party  │  │  Streaming  │
  │ (clicks,    │  │  (user info,│  │  Signals    │  │  Logs       │
  │  purchases) │  │   orders)   │  │ (weather,   │  │  (Kafka)    │
  └──────┬──────┘  └──────┬──────┘  │  credit)    │  └──────┬──────┘
         │                │         └──────┬──────┘         │
         └────────────────┴────────────────┴────────────────┘
                                    │
                                    ▼
  FEATURE PIPELINE  ┌──────────────────────────────────────┐
                    │  Raw data → cleaned, joined, computed │
                    │  features (ETL / Spark / Flink)       │
                    └──────────────────┬───────────────────┘
                                       │
                    ┌──────────────────▼───────────────────┐
  FEATURE STORE     │   Offline Store  │   Online Store     │
                    │  (BigQuery/Hive) │  (Redis/DynamoDB)  │
                    │  batch training  │  real-time serving │
                    └────────┬─────────┴──────────┬─────────┘
                             │                    │
              ┌──────────────▼──────┐    ┌────────▼──────────────┐
  TRAINING    │  Training Pipeline  │    │   Serving Pipeline    │  SERVING
  PIPELINE    │  (Spark ML, TF,     │    │   (model server:      │
              │   PyTorch)          │    │    TF Serving,        │
              └──────────┬──────────┘    │    Triton, custom)    │
                         │               └────────┬──────────────┘
              ┌──────────▼──────────┐             │
  MODEL       │   Model Registry    │─────────────┘
  REGISTRY    │   (MLflow, Vertex   │  (deploy model to server)
              │    AI, SageMaker)   │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
  MONITORING  │  Drift Detection +  │
              │  Performance Metrics│
              │  + Alerting         │
              └──────────┬──────────┘
                         │
                         ▼
              ┌──────────────────────┐
  FEEDBACK    │  Labels from user    │◀── user clicks, purchases,
  LOOP        │  behavior → back to  │    conversions, complaints
              │  feature pipeline    │
              └──────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
```

Every interview for an ML system design question is really about designing this diagram. The
question just tells you which part to emphasize. Fraud detection → emphasize real-time feature
pipeline and serving latency. Recommendation → emphasize candidate generation and ranking.
Search → emphasize retrieval and training data quality.

### Intern → Staff Progression (Part 2)

| Level | How they read the full ML system architecture |
|-------|----------------------------------------------|
| **Intern** | Sees the serving box. "We deploy the model." Does not notice the other seven boxes exist. |
| **L3** | Sees training + serving as two separate boxes. Connects them by manually copying a .pkl file from the training machine to the server. |
| **L4** | Notices the feature store box. Realizes training and serving must read features from the same place to avoid skew. Starts asking "how do we keep these in sync?" |
| **L5** | Sees the feedback loop arrow and understands it as a risk. Designs the monitoring box with real alerts. Understands that the model registry is a versioning system, not just a file folder. |
| **L6** | Reads the entire diagram as a failure domain map. Asks: "What happens when each box fails? What happens when the feedback loop teaches the model the wrong thing? How do we safely swap out the model in the registry without breaking serving? Who owns each box, and what are their SLAs?" Treats the diagram as a living system, not a static architecture. |

### Brainstorming Questions (Part 2)

**Q: The diagram shows a feedback loop. What happens when the feedback loop teaches the model the wrong thing?**

The feedback loop is the arrow from user behavior back into the training data. It looks helpful — you get fresh labels automatically, so the model keeps learning. The danger is that the model's own decisions are shaping what it learns next. If the model recommends item A and the user clicks item A, the model learns "item A is good." But the user only clicked item A because the model showed it to them — they never had a chance to click item B. Over time, the model gets more and more confident about items it already likes, and less and less able to discover that item B might have been better.

This is not a hypothetical. Twitter's algorithmic timeline did exactly this. The model learned that outrage-generating content drives engagement clicks, so it surfaced more of that content, users clicked on it (often in anger), and those clicks trained the next model to surface even more outrage content. The feedback loop was working perfectly — it was accurately learning from real user behavior. The problem was that the user behavior it was learning from was behavior the model itself had caused, not behavior that reflected what users actually wanted.

The fix has two parts. First, add an **exploration budget**: randomly inject content the model did not rank highly, and log those results separately as "exploration data." This gives you an unbiased signal about items outside the model's current preferences. Second, choose a **better training signal**: instead of optimizing for clicks (which the model can game by picking outrage content), optimize for a signal that is harder to manipulate, like satisfaction surveys, return visits, or time to next session. The feedback loop will still exist, but it will be learning from a healthier signal.

---

**Q: The architecture has a model registry between training and serving. Why not deploy models directly from training to serving?**

Imagine the training pipeline is a factory that produces model files. If you deploy models directly to the serving fleet the moment they come out of the factory, you have no quality gate. A training job that runs with corrupt data, wrong hyperparameters, or a bug in the preprocessing code will push a broken model to production automatically. Users will see bad predictions immediately, and by the time anyone notices, the model has already been running for hours.

The model registry is the quality gate. It is the checkpoint where the model must prove itself before being trusted in production. In a well-designed system, a model gets promoted to the registry only after: (1) it beats a minimum quality bar on the offline test set, (2) it beats the currently deployed model in a shadow test on recent production data, and (3) a human or automated system reviews the evaluation report and approves the promotion. The registry stores the model artifact plus all the metadata: training date, data version, evaluation metrics, feature list, and who approved it. This audit trail is what lets you trace a problem in production back to exactly which training run caused it.

There is also a practical infrastructure reason. The training pipeline runs on a GPU cluster or Spark cluster — a very different environment from the prediction server fleet. The model registry decouples these two environments. Training writes to the registry; serving reads from it. If the training cluster goes down, serving keeps running the last good model from the registry. If the serving fleet needs to roll back, it reads an older registry entry. Without the registry as a buffer, an outage in training could cascade into an outage in serving.

---

**Q: How does this architecture change if you are building an ML system for a startup with 10K users vs a tech giant with 1B users?**

At 10K users, most of the boxes in the full architecture diagram are premature. You do not need a feature store — a Postgres query can compute your features fresh for every prediction request, and with 10K users the database will handle it. You do not need a model registry — you have one model, one engineer, and you can manually track the model file in git. You do not need drift detection infrastructure — you can look at a dashboard once a week and notice if business metrics are dropping. The right architecture for 10K users is: write features in a script, train a model in a notebook, serve it as a Flask API, log predictions to a CSV. Ship in two weeks, not six months.

At 1B users, every box in the diagram exists because the cost of not having it is catastrophic. Without a feature store, you have 50 teams each writing their own feature logic, accumulating skew bugs that nobody can track down. Without a model registry, a bad training run deploys directly to 1B users before anyone notices. Without drift detection, a model goes stale and your revenue drops by 3% for three months before someone correlates the dates. At this scale, each component in the diagram exists because a real company hit the pain of not having it and built the tool to fix it. The architecture grew out of failure, not planning.

The practical lesson for interviews: always ask "what scale?" before designing. An ML system for a startup and an ML system for a tech giant look completely different. The interviewer who asks "design a recommendation system" might want you to build for Netflix scale or might want you to build for a 50-person SaaS company. Clarifying scale is the first question to ask, and the answer completely changes which boxes you need to build.

### Real Incident (Part 2): Twitter's Algorithmic Timeline and the Feedback Loop Gone Wrong

In 2016, Twitter switched from a chronological timeline to an algorithmic one. The model was designed to predict which tweets a user would "engage" with — meaning reply to, retweet, or click on. By that metric, the model worked very well. Engagement went up. The model was succeeding at its objective.

What the model had quietly learned was that high-emotion content — outrage, controversy, heated arguments — generates more engagement than calm, informative content. A tweet that makes you angry makes you more likely to reply or quote-tweet it. So the model surfaced more of that content. Users saw it, engaged with it, and those engagement signals became training data for the next model. The feedback loop had created a self-reinforcing cycle: outrage content drove engagement, engagement trained the model, the model served more outrage content.

The technical lesson is about the architecture, not the model itself. The model registry, the feedback loop, and the training pipeline were all working as designed. The failure was in the full-system design: there was no mechanism to check whether the feedback loop was teaching the model something harmful. The monitoring tracked engagement metrics (clicks, retweets) and those were going up — so from a monitoring standpoint, everything looked healthy. What was missing was a **feedback loop audit**: a periodic check that asks "what is the model learning from this loop, and is that what we want it to learn?" At L6, this means designing monitoring that goes beyond input and prediction distributions, to monitoring what the training data composition looks like over time — are certain types of content being increasingly overrepresented in the feedback signal?

---

## Part 3: Feature Store — The Central Component

### What is a Feature?

Think of an ML model like a very sophisticated Excel formula. The formula takes columns as
inputs and produces a number as output. Those columns are **features**. In a SQL query, you
write `SELECT age, city, purchase_count FROM users`. In ML, those same columns are features.

The difference is that ML features are often computed from raw data on the fly. "Number of
purchases in the last 7 days" is not stored anywhere — it must be computed by scanning the
purchases table. Features are **derived columns** that may require complex computation.

A **feature store** is a system that computes, stores, and serves features — both for training
(where you need historical values across millions of users) and for serving (where you need
the current value for one user in under 10ms).

### Online vs Offline Feature Store

Think of this split like the difference between a data warehouse and a cache. They store the
same information, but they are optimized for completely different access patterns.

```
FEATURE STORE ARCHITECTURE

  Raw Data (user events, transactions, etc.)
         │
         ▼
  ┌─────────────────────────────────────────────┐
  │           Feature Computation Layer          │
  │   (Spark for batch / Flink for streaming)   │
  └───────────────────┬──────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
  ┌───────────────┐       ┌───────────────┐
  │  OFFLINE      │       │   ONLINE      │
  │  STORE        │       │   STORE       │
  │               │       │               │
  │  BigQuery /   │       │  Redis /      │
  │  Hive / S3    │       │  DynamoDB /   │
  │               │       │  Cassandra    │
  │  - Historical │       │               │
  │    snapshots  │       │  - Latest     │
  │  - Terabytes  │       │    value only │
  │  - Query in   │       │  - Key-value  │
  │    seconds    │       │  - Query in   │
  │  - Used for   │       │    <10ms      │
  │    training   │       │  - Used for   │
  └───────────────┘       │    serving    │
                          └───────────────┘
       │                        │
       ▼                        ▼
  Training jobs           Prediction server
  (reads history)         (reads latest)
```

**Offline store** (for training): "Give me the value of feature X for every user, as of January
1st." You run a big batch query. It returns billions of rows. Slow is fine — training takes
hours anyway.

**Online store** (for serving): "Give me the value of feature X for user_id=123 right now." It
must return in under 10 milliseconds. You look it up by key, like a cache hit.

### The Training-Serving Skew Problem

This is the most common — and most expensive — bug in ML systems. Here is how it happens:

**In training**, a data scientist writes Python code to compute features from historical data:
```python
# Training code (Python, runs on Spark)
df['purchase_rate_7d'] = df.groupby('user_id')['purchase'].rolling('7d').sum()
```

**In serving**, an engineer writes the same feature in Java to run fast in the prediction server:
```java
// Serving code (Java, runs in prod)
double purchaseRate7d = redisClient.get("purchase_rate_7d:" + userId);
```

These two computations should produce the same number. But in practice:
- The Python code uses UTC. The Java code uses local time.
- The Python code counts cancelled orders. The Java code does not.
- The Python code uses a rolling 7-day window. The Redis key is updated every hour.

The model was trained expecting feature values in one range. It is served feature values in a
slightly different range. Its accuracy degrades. Nobody notices for weeks because the degradation
is gradual.

**The fix:** A feature store with a single computation definition. You write the feature logic
once, and the same code runs in both training (batch mode) and serving (streaming/real-time
mode). This is the core value proposition of Feast, Tecton, and similar tools.

### Concrete Training-Serving Skew Example

Here is a real-world example of how skew happens. The bug is subtle — read both code blocks
carefully and find the difference before reading the annotation.

```python
# ─────────────────────────────────────────────────────────
# TRAINING CODE (Python/Spark, runs nightly on EMR cluster)
# ─────────────────────────────────────────────────────────
def compute_user_purchase_count_7d(user_events_df):
    """
    Compute how many purchases a user made in the last 7 days.
    Used as a feature for churn prediction training.
    """
    return (
        user_events_df
        .filter(col("event_type") == "purchase")
        .filter(col("timestamp") >= current_date() - 7)   # ← last 7 calendar days
        .groupBy("user_id")
        .agg(count("*").alias("purchase_count_7d"))
    )
    # NOTE: No filter on order status. Counts ALL purchase events,
    # including cancelled and refunded orders.
```

```python
# ─────────────────────────────────────────────────────────
# SERVING CODE (Python/Flask, runs at prediction time)
# ─────────────────────────────────────────────────────────
def compute_user_purchase_count_7d(user_id: str, db) -> int:
    """
    Compute how many purchases a user made in the last 7 days.
    Called in the prediction server when serving churn predictions.
    """
    row = db.execute("""
        SELECT COUNT(*) as purchase_count
        FROM orders
        WHERE user_id = %s
          AND event_type = 'purchase'
          AND created_at >= NOW() - INTERVAL '7 days'
          AND status = 'completed'           -- ← BUG: training didn't filter by status!
    """, (user_id,)).fetchone()
    return row["purchase_count"]
```

**The bug:** Training counts all purchase events (including cancelled and refunded orders).
Serving counts only completed orders. A user who placed 10 orders but cancelled 8 of them
would get `purchase_count_7d = 10` in training data, but `purchase_count_7d = 2` at serving
time. The model trained on inflated counts is served deflated counts. Its churn probability
estimates for heavy-but-cancelled-order users will be systematically wrong.

**Why this is hard to detect:** The values are in the same range (both are counts of
purchases), so the distributions look similar at first glance. The bug shows up as a
gradual accuracy gap between training metrics and production metrics — the kind of gap
that takes weeks to notice and another week to diagnose.

**How to find it:** Log the actual feature values that your serving layer sends to the
model for a random sample of predictions. Store them alongside the ground-truth feature
values computed by the training pipeline for those same users at those same timestamps.
Plot the distribution of both. If they differ, you have found your skew.

**How to prevent it:** Write one canonical feature definition:

```python
# ─────────────────────────────────────────────────────────
# FEAST FEATURE DEFINITION (single source of truth)
# ─────────────────────────────────────────────────────────
# feast/features/user_purchase_features.py

from feast import Feature, FeatureView, FileSource
from feast.types import Int64
from datetime import timedelta

user_purchase_stats_view = FeatureView(
    name="user_purchase_stats",
    entities=["user_id"],
    ttl=timedelta(days=1),           # ← online store expires after 1 day
    features=[
        Feature(name="purchase_count_7d", dtype=Int64),
        Feature(name="completed_purchase_count_7d", dtype=Int64),
    ],
    source=FileSource(path="s3://my-bucket/user_purchase_stats/*.parquet"),
    # The computation logic lives in the transformation below.
    # The SAME transformation runs during training (batch) and
    # during serving (loaded from online store populated by this same logic).
)
```

The Feast framework runs the same transformation in batch (for training data) and keeps
the online store (Redis) populated with the latest values computed by the same logic.
You cannot have a skew bug because there is only one definition.

### Common Mistakes — Part 3: Feature Store

```
COMMON MISTAKES IN FEATURE STORE DESIGN

Mistake 1: Writing feature logic twice (once for training, once for serving)
Symptom: Production accuracy is 5-15% lower than test accuracy. The gap exists
from day one of deployment and never improves.
Root cause: The two implementations compute slightly different values (timezone
differences, NULL handling, filter conditions, rounding).
Fix: Write a single feature definition (using Feast, Tecton, or a shared Python
library) that the same code path executes in both batch and streaming modes.

Mistake 2: Putting everything in the online store
Symptom: Your Redis cluster costs more than your model servers. You are hitting
Redis for features that only change once a day.
Root cause: Treating all features as if they need real-time freshness.
Fix: Audit each feature for actual freshness requirements. A user's demographic
data (age, city) can be refreshed daily via batch and looked up from a simple DB
table. Only features that change minute-to-minute (session activity, recent
purchase count) belong in the online store.

Mistake 3: Not handling missing features gracefully
Symptom: When a new user makes their first request, the feature lookup returns
NULL for historical features (no history exists yet). The model receives NULL
and produces a garbage prediction or crashes.
Fix: Define explicit default values per feature. "purchase_count_7d" defaults to
0 for new users. "avg_session_duration_sec" defaults to the population median.
Store these defaults in the feature store definition, not in ad-hoc serving code.

Mistake 4: Forgetting point-in-time correctness in training
Symptom: Model appears to predict the future (suspiciously high accuracy). Label
leakage: training features include values from after the prediction timestamp.
Example: you predict churn on Jan 1 using "days since last purchase" — but you
computed "days since last purchase" using Feb data, which shows the user had
already churned. The model sees the future.
Fix: When generating training data, always compute feature values as of the
prediction timestamp. Feast's get_historical_features() API does this automatically.
```

### Feature Freshness

Not all features need to be up-to-the-second. The key question: **how much does prediction
quality degrade as this feature gets stale?**

```
FEATURE FRESHNESS SPECTRUM

  Freshness needed: HOURS/DAYS          Freshness needed: REAL-TIME (<1min)
  ─────────────────────────────────────────────────────────────────────────▶
  
  "User's              "User's           "User's last      "Was this card
   demographic          favorite           login time"       used at two
   info (age,city)"     genre"                               locations in
                                                             the last 5min?"
  
  ← Batch OK ─────────────────────────────── Streaming required →
  
  Risk if stale:  LOW                                           HIGH
  Cost to freshen: LOW                                          HIGH
```

A fraud signal ("was this card used at two ATMs in different cities in the last 5 minutes") must
be real-time. If your feature is 10 minutes stale, you approve a fraudulent transaction. A user's
age does not change in a day — batch computation every 24 hours is fine.

The engineering cost scales with freshness requirements. Real-time features require streaming
pipelines (Kafka + Flink), which are much harder to operate than batch pipelines (Spark jobs).
A key L6 skill is matching freshness requirements to pipeline complexity — do not build a
streaming pipeline when a batch pipeline would work fine.

### Real-World Feature Stores

- **Uber Michelangelo** (2017): Uber built this internal platform after finding that every team
  had their own feature computation logic, causing training-serving skew across all their ML
  models. Michelangelo introduced a shared feature store that all teams write to and read from.
  
- **Airbnb Zipline** (2018): Airbnb built Zipline to support their search ranking and pricing
  models. Key innovation: the same feature declaration works for both training and serving,
  eliminating skew by construction.

- **Feast** (open source): Started at Gojek, now widely used. Provides both an offline store
  (BigQuery or Parquet files) and an online store (Redis or DynamoDB). Teams write feature
  definitions in Python once; Feast handles both training data generation and online serving.

- **Google's internal feature store**: Part of their Vertex AI platform. Integrated with
  BigQuery for offline and Bigtable for online. Used across Google Search, Ads, and YouTube.

### Intern → Staff Progression (Part 3)

| Level | Feature store understanding |
|-------|----------------------------|
| **Intern** | Computes features in the same training script. Doesn't think about serving. |
| **L3** | Realizes features need to be recomputed for serving. Writes the same logic twice (skew risk). |
| **L4** | Discovers skew bugs in prod. Pushes for shared computation. Starts building a rudimentary feature cache. |
| **L5** | Designs a feature pipeline with separate offline (batch) and online (streaming) legs. Monitors freshness. |
| **L6** | Designs a full feature store: unified feature definitions, SLA per feature, freshness monitoring, automatic backfilling for new features, point-in-time correct training data generation. |

### Brainstorming Questions (Part 3)

**Q: Your team is building a churn prediction model. The model needs 50 features. How do you
decide which features go in the online store vs offline store?**

Start by asking what happens if the prediction is stale. Churn prediction is typically run once
a day — the system identifies users at risk of churning and triggers a retention campaign (email,
discount). This is a **batch serving** use case, not real-time. That means you do not need an
online store at all — you compute predictions nightly, store results in a table, and your
campaign system reads from that table.

Given batch serving, all 50 features can live in the offline store. You run a big Spark job that
reads historical data, computes all 50 features for every user as of yesterday, writes that to
a training dataset, and also writes the latest values to a "prediction features" table. The
model reads from the prediction features table. No Redis, no streaming — just scheduled batch
jobs. This is cheaper, simpler, and easier to debug than an online store.

The only exception: if a feature represents something that changed today (a user's account
cancellation click from 2 hours ago), and including it would significantly improve prediction
quality, then that specific feature needs fresher computation. Even then, you might set up an
hourly batch job rather than a streaming pipeline — hourly is "fresh enough" and much simpler
to operate.

---

**Q: You notice that your model's accuracy in production is significantly lower than its accuracy
on the test set during training. What are the possible causes and how do you investigate?**

The most likely cause is **training-serving skew**. The features seen during training are
computed differently from the features seen in production. Begin the investigation by logging
the actual feature values that the model receives in production for a sample of predictions.
Then, for those same users and timestamps, recompute what the features "should" have been using
the training pipeline. Compare the distributions. If they differ significantly (different mean,
different variance, different null rate), you have found your skew.

A second possibility is **label leakage** in training: your training data accidentally included
information from the future that would not be available at prediction time. This makes the model
look great on the test set but perform poorly in reality because it was trained on cheated data.
For example, if you include "account closed in next 30 days" as a feature (which is derived from
the future), the model learns to predict churn with unrealistic accuracy. Always check: for each
feature in training, was this value actually available at the time the prediction would have been
made?

A third cause is **dataset shift**: the training data distribution does not represent the
production distribution. Maybe you trained on US users but are serving globally, or you trained
on data from 6 months ago and user behavior has since changed. Look at the distribution of input
features in training vs production — plot histograms, compute statistical tests (KL divergence,
PSI). If the distributions look very different, you need to retrain on data that better
represents what you are seeing in production.

---

**Q: A new regulation requires that features derived from user location cannot be used in your
model. How do you handle this without retraining from scratch?**

The first thing to understand is that "not using location" is more subtle than removing a column.
Other features may be proxies for location — ZIP code → neighborhood → income level, for example.
Regulatory compliance often requires an audit of all feature correlations with the protected
attribute, not just removal of the direct feature. This is a data governance problem as much as
an engineering problem.

From an engineering standpoint, removing features from a feature store is straightforward: add
them to a blocklist in the feature serving layer so they return null regardless of what is
computed. But you also need to retrain the model without those features, because a model trained
with location features and then served without them (nulled out) is not the same as a model that
never saw location. The model has learned to rely on location; removing it mid-flight gives it
corrupted inputs.

The operational procedure: first, add the blocklist (this is a quick compliance fix that stops
the model from using the features even if the model weights still depend on them — imperfect but
quick). Then, in parallel, retrain a new model version on data with those features removed or
masked. Test it extensively to confirm no proxy features sneak location signals back in. Run
it in shadow mode alongside the old model. Once quality is confirmed acceptable, promote it.
Document the whole process for the compliance audit.

---

## Part 4: Training Pipeline

### What Happens in Training

Imagine teaching a new employee how to do loan approvals. You give them 10,000 past loan
applications with the outcome (paid back or defaulted). They study the pattern and learn: high
debt-to-income ratio + short employment history = high default risk. That pattern, encoded as
math, is the model.

**Training pipeline stages:**

```
TRAINING PIPELINE

  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  ① DATA COLLECTION                                            │
  │     Pull labeled examples from offline feature store          │
  │     "Users who churned" / "Transactions that were fraud"       │
  │                          │                                    │
  │                          ▼                                    │
  │  ② DATA VALIDATION                                            │
  │     Schema check: are all expected features present?          │
  │     Distribution check: did any feature shift dramatically?   │
  │     Label check: is the label distribution reasonable?        │
  │                          │                                    │
  │                          ▼                                    │
  │  ③ FEATURE EXTRACTION                                         │
  │     Join features from multiple tables                        │
  │     Handle missing values (imputation)                        │
  │     Encode categoricals, normalize numerics                   │
  │                          │                                    │
  │                          ▼                                    │
  │  ④ MODEL TRAINING                                             │
  │     Train/validation/test split (time-based!)                 │
  │     Hyperparameter tuning                                     │
  │     Fit model on training set                                 │
  │                          │                                    │
  │                          ▼                                    │
  │  ⑤ EVALUATION                                                 │
  │     Evaluate on test set (held-out data)                      │
  │     Check: better than current production model?              │
  │     Check: business metrics (precision/recall at threshold)?  │
  │                          │                                    │
  │                          ▼                                    │
  │  ⑥ MODEL REGISTRY                                             │
  │     Serialize model to file                                   │
  │     Register in model registry with metadata                  │
  │     (accuracy, training date, feature list, data version)     │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

### Batch Training vs Online Learning

**Batch training** is the default. You collect data over a period (a week, a month), run a big
training job, produce a new model, and deploy it. Simple. Works for most cases.

**Online learning (streaming training)** is when the model updates itself continuously on each
new data point. Think of it as the model learning as it goes. This is necessary when the world
changes so fast that a weekly retrain is too slow — for example, ad click prediction, where the
trending topics today are completely different from yesterday.

The engineering complexity of online learning is much higher: you need to handle concept drift
at training time, ensure the streaming pipeline delivers data in order, detect when the model
is updating in a bad direction and roll back, and serve a model that is being updated while
simultaneously taking live traffic. Most teams use batch training for most models.

### When to Retrain

Three triggers for retraining:

1. **Scheduled**: Retrain every 24 hours regardless of model quality. Simple but wasteful if
   the model is still good, and slow to respond if the model degrades between retrain windows.

2. **Performance-triggered**: Monitor model quality metrics. When accuracy drops below a
   threshold, trigger retraining. Requires good monitoring. Has a lag — the model is bad for
   some time before the trigger fires.

3. **Drift-triggered**: Monitor input feature distributions. When they shift significantly,
   trigger retraining proactively, before model quality degrades. Faster response but may
   trigger unnecessary retrains if drift does not actually affect model quality.

### The Time-Based Split Problem

In a standard ML course, you split your dataset randomly: 80% training, 10% validation, 10% test.
That is wrong for production systems. Here is why: if you are predicting whether a user will churn
next month, and you have data from January through December, a random split might put some
January data in your test set. Your model learns from December data to predict users who were
already known to have churned in January. That is cheating — the model would never see future
data in production.

The correct approach is **time-based splitting**: train on January through September, validate
on October, test on November and December. The model is always evaluated on data that comes
after its training period, mimicking how it will be used in production.

### Real Example: Netflix Model Retraining Pipeline

Netflix's recommendation model retraining is a well-known example of production ML complexity.
Their training pipeline must handle: terabytes of daily interaction data (plays, pauses, ratings),
point-in-time correct feature computation (what did this user's watch history look like at the
moment they received the recommendation, not their current history), training on a cluster that
costs tens of thousands of dollars per run, and evaluation against multiple business metrics
(not just accuracy — also diversity, novelty, and serendipity of recommendations). Their pipeline
is a directed acyclic graph (DAG) of dozens of steps, orchestrated by an internal tool similar
to Apache Airflow.

### Common Mistakes — Part 4: Training Pipeline

```
COMMON MISTAKES IN TRAINING PIPELINE DESIGN

Mistake 1: Random train/test split on time-series data
Symptom: Offline accuracy is 92%; production accuracy is 71%. Massive gap.
Root cause: A random 80/20 split puts some February data in training and some
January data in the test set. The model sees the future in training. When it
runs on actual future data (production), the shortcut is gone.
Fix: ALWAYS use time-based splits. Train on months 1-9, validate on month 10,
test on months 11-12. Test set must come strictly after training set in time.

Mistake 2: No data validation before training
Symptom: Training job completes with no errors. New model performs terribly in
production. Days of debugging reveal that the training data had a 40% null rate
on a key feature due to an upstream schema change.
Fix: Add data validation as the first step of the training DAG. Check: schema
matches expected schema, null rates are within expected bounds, label
distribution is within expected range. Fail fast: if validation fails, do NOT
run training on corrupt data. Alert and block the run.

Mistake 3: Evaluating against a single global accuracy metric
Symptom: Model accuracy is 94% on the test set. The model is deployed. Within
a week, you discover it is performing terribly for users in Asia (only 20% of
your training data was from non-US users).
Fix: Evaluate on slices: per geography, per user cohort, per device type, per
time window. An overall accuracy of 94% can hide a 50% accuracy for a specific
sub-group. Slice-based evaluation is mandatory for fair, production-ready models.

Mistake 4: Not saving the exact training configuration for reproducibility
Symptom: A model from 6 months ago caused a bad decision. You are asked to
reproduce that exact model to understand why. You cannot. The training code has
changed, the data has been overwritten, and the hyperparameters were never logged.
Fix: Log everything to the model registry: git commit hash of training code,
data snapshot version (S3 path + timestamp), all hyperparameters, evaluation
metrics, training duration, hardware used. With this, you can reproduce any
training run exactly.
```

### Intern → Staff Progression (Part 4)

| Level | Training pipeline thinking |
|-------|---------------------------|
| **Intern** | Runs training in a Jupyter notebook. Pushes the .pkl file manually to prod. |
| **L3** | Scripts the training. Can reproduce runs. Does not validate data quality before training. |
| **L4** | Adds data validation. Uses time-based splits. Automates the training job on a schedule. |
| **L5** | Builds a DAG-based pipeline. Adds model evaluation gates (must beat baseline). Integrates with model registry. |
| **L6** | Designs the full pipeline with data lineage tracking, drift-triggered retraining, automatic rollback if new model is worse, training cost monitoring, and reproducibility (given a model version, can exactly reproduce the training run). |

### Brainstorming Questions (Part 4)

**Q: Your training job runs for 6 hours and costs $2,000 in compute. The data science team wants
to retrain every 3 hours to stay fresh. How do you address this?**

The first instinct is to say "no" — but the right response is to understand why they want 3-hour
retrains. What is the model? What changes every 3 hours that makes a retrained model materially
better? If the model is a news recommendation model and trending topics change hourly, then yes,
more frequent retraining genuinely helps. If the model is a user churn predictor and user behavior
changes slowly, then daily or weekly retraining is almost certainly sufficient.

If the business case for 3-hour retrains is genuine, the answer is not to run the same 6-hour
job 8 times a day. The answer is to make the training job faster. Options: train on only recent
data (last 7 days instead of last 6 months — reduces data size dramatically); use incremental
training (warm-start from the previous model, only update on new data); or use online learning
for the component that changes most rapidly while keeping batch training for the stable components.
Google's ad CTR prediction uses FTRL (online learning) because ad click patterns change on an
hourly basis — they literally cannot batch-retrain fast enough.

The 6-hour runtime also needs investigation. Is it data loading, feature computation, or actual
model training? Profiling the pipeline often reveals that 80% of the time is spent on data
loading and feature computation, not model training. Caching computed feature datasets between
runs can dramatically cut runtime without any model quality loss.

---

**Q: You discover that 30% of the labels in your training data are incorrect. What do you do?**

Incorrect labels are actually the most common data quality problem in production ML, and 30% is
severe but not unusual for systems where labels come from user behavior rather than human
annotation. First, understand why the labels are wrong. There are two main causes: label noise
(genuine uncertainty — the user clicked an ad but did not actually want it) and labeling bugs
(a code error in the pipeline that computes labels from raw events, such as counting a browser
refresh as a second impression).

If the labels are wrong due to a pipeline bug, fix the bug and recompute labels from the raw
event log. This is painful — it means regenerating your entire training dataset — but it is
mandatory. Training on incorrect labels due to a bug trains the model to learn the bug, not the
actual behavior. Once fixed, your model will likely improve significantly.

If the labels have genuine noise (for example, "did the user like this recommendation" is
inherently ambiguous — they watched it but gave it 2 stars), you have several options. Label
smoothing (a training technique) handles some noise gracefully. Confidence-weighted training
(upweight examples where you are confident in the label, downweight uncertain ones) is another
approach. You can also add a human review step for borderline cases to get cleaner signal.
Either way, establish ongoing label quality monitoring — track the label distribution weekly and
alert if it shifts more than expected.

---

**Q: How do you design a training pipeline that can be audited six months later to understand
exactly how a model that caused harm made a specific decision?**

This is a model governance and reproducibility problem, and it is increasingly important for
regulated industries (banking, healthcare, insurance). The goal is: given a model prediction
made on a specific date for a specific user, be able to reproduce that prediction exactly and
explain every feature value that contributed to it.

The key insight is that you need to log two things at prediction time: the model version identifier
and the exact feature values used for that prediction. The model version identifier lets you load
the exact model weights. The feature values let you verify that the model ran on the expected
inputs. Both must be stored in a durable, immutable store (append-only log, like S3 or BigTable)
with a retention policy measured in years for regulated use cases.

For the training pipeline itself, reproducibility requires: versioning the training code (git
commit), versioning the training data (data snapshot or pointer to the exact date/time of the
data pull), logging all hyperparameters, and recording the evaluation metrics at training time.
Tools like MLflow, DVC, and Vertex AI Experiments track these automatically if you instrument
your training code. The model registry stores all of this metadata alongside the model artifact.
When an audit happens 6 months later, you can pull the model artifact, the training code commit,
and the exact data snapshot, rerun the training, and confirm the model is identical to what was
deployed.

---

## Part 5: Model Serving — Online vs Batch

### The Two Serving Modes

Serving is how predictions reach users. There are exactly two modes, and choosing between them
is one of the most impactful architectural decisions in an ML system.

**Online serving** is synchronous. The user does something (clicks search, initiates payment),
your API receives a request, you compute the prediction in real time, you return it. The user
waits. This means predictions are fresh and context-aware, but latency requirements are strict
(p99 < 100ms for most user-facing systems).

**Batch serving** is asynchronous. You precompute predictions for many users at once (nightly),
store the results in a table, and when the user interacts, you look up their precomputed
prediction. Zero latency at request time (it is just a database read), but predictions may be
hours old.

```
ONLINE SERVING                          BATCH SERVING

User Request                            Nightly Job
     │                                       │
     ▼                                       ▼
 API Server  ────── feature lookup ──▶  Prediction
     │              (online store)      for all users
     │                                       │
     │         Model Inference               ▼
     │         (real-time)             Results Table
     │                                 (BigQuery/DynamoDB)
     ▼                                       │
 Response ◀──── prediction                   │
 (<100ms)                              User Request
                                             │
                                             ▼
                                       Read from table
                                       (< 5ms lookup)
                                             │
                                             ▼
                                         Response

Use when:                               Use when:
- Decision must be made at             - Prediction can be
  request time (fraud, search)           precomputed (emails,
- Context matters (user's              - Latency budget is
  current session behavior)              very tight (no time
- Freshness is critical                  for inference at request)
                                       - Millions of users need
                                         predictions simultaneously
```

### The Latency Budget Problem

If your API has a 200ms latency budget and you allocate 180ms to the ML model, you have 20ms
left for: reading the user's features from the online store, network overhead, serialization,
and returning the response. That is not enough. The model must be fast enough to fit in your
latency budget after everything else is accounted for.

The latency budget analysis is a critical part of L6 ML system design. You must know (roughly):
- Redis lookup: 1-5ms
- Database query: 5-50ms
- Model inference, simple model (logistic regression, XGBoost): 1-10ms
- Model inference, large neural network: 10-100ms
- Model inference, large language model: 100ms-5 seconds

If the model is too slow, options: switch to a faster model (trade accuracy for latency), run
the model on GPU (expensive but fast), quantize the model (reduce precision, reduce size and
latency), cache predictions (pre-compute for likely inputs), or switch to batch serving.

### Deployment Patterns

```
MODEL DEPLOYMENT PATTERNS

  SHADOW MODE (before release)
  ┌────────────────────────────────────┐
  │  All traffic → Old Model → Users  │
  │       ↕                           │
  │  Same traffic → New Model         │  ← New model gets same inputs
  │  (predictions logged, not served) │    but predictions are NOT
  │                                   │    shown to users. Just logged.
  └────────────────────────────────────┘
  Purpose: validate new model on real traffic without risk

  CANARY DEPLOYMENT (low confidence)
  ┌────────────────────────────────────┐
  │  95% traffic → Old Model          │
  │   5% traffic → New Model ─────────│──▶ Both serve real users
  └────────────────────────────────────┘
  Purpose: early signal with limited blast radius

  A/B TEST (comparison)
  ┌────────────────────────────────────┐
  │  50% traffic → Model A (control)  │
  │  50% traffic → Model B (variant)  │
  └────────────────────────────────────┘
  Purpose: statistically significant comparison

  FULL ROLLOUT
  ┌────────────────────────────────────┐
  │  100% traffic → New Model         │
  └────────────────────────────────────┘
```

### What a Model Serving Request/Response Actually Looks Like

Candidates often talk abstractly about "the model server." Here is what an actual request
and response look like in a real ML serving system (using TF Serving's REST API format):

```json
// REQUEST: Sent from the application server to the model server
// POST http://ml-serving.internal:8501/v1/models/recommendation_v42:predict

{
  "signature_name": "serving_default",
  "instances": [
    {
      "user_id": "u_12345678",
      "user_features": {
        "age_bucket": 2,
        "account_age_days": 583,
        "purchase_count_7d": 12,
        "avg_session_duration_sec": 247,
        "preferred_categories": [3, 7, 12],
        "last_login_days_ago": 1
      },
      "candidate_item_ids": [
        "item_991234", "item_774421", "item_883312",
        "item_116643", "item_228874"
      ],
      "context": {
        "device_type": "mobile",
        "hour_of_day": 19,
        "day_of_week": 5,
        "session_page_count": 3
      }
    }
  ]
}
```

```json
// RESPONSE: Returned by the model server, typically in < 50ms

{
  "predictions": [
    {
      "item_scores": {
        "item_991234": 0.847,
        "item_883312": 0.812,
        "item_228874": 0.731,
        "item_774421": 0.523,
        "item_116643": 0.398
      },
      "model_version": "recommendation_v42",
      "inference_time_ms": 23,
      "serving_mode": "online"
    }
  ]
}
```

The application server receives the scores, applies post-ranking business logic (diversity
filters, freshness boosts, safety filters), and returns the final ranked list to the user.

**What happens when the model server is down:**

```
MODEL SERVER REQUEST (timeout after 150ms)
        │
        │  150ms passes with no response
        │
        ▼
  CATCH TimeoutException
        │
        ▼
  FALLBACK: read pre-computed batch predictions
  from Redis: GET user:12345678:batch_recs
  └── returns: ["item_991234", "item_774421", ...]
       (computed in last nightly batch job, up to 24h old)
        │
        ▼
  IF batch_recs ALSO missing (new user, or expired):
  └── fall back to popularity-based top-20
       (top 20 items by platform-wide CTR, updated hourly)
        │
        ▼
  Log: {"serving_mode": "fallback", "reason": "model_timeout",
        "user_id": "u_12345678", "ts": "2024-01-15T19:34:21Z"}
  Alert: if fallback_rate > 1% in last 5 minutes → PagerDuty
```

This fallback chain is what separates an L6 serving design from an L5 one. The L5 engineer
designs the happy path. The L6 engineer designs the fallback hierarchy for every failure mode.

### Real Examples

**Airbnb search ranking (online serving):** When a user searches for a listing, the ranking must
happen in real time — the results depend on the user's current filters, location, travel dates,
and price range. All of these are session-level context that does not exist before the search.
Airbnb must compute search rankings in under 100ms for every search query.

**Netflix recommendations (batch serving):** Netflix's "recommended for you" row is precomputed
nightly for every user. When you open the app, your recommendations are looked up from a table —
zero inference latency. This works because Netflix recommendations do not depend on your current
session context (what you just searched). They depend on your long-term watch history, which
changes slowly. Precomputing nightly is fresh enough.

### Concrete Latency Budget: How to Break Down 200ms

One of the most common L6 mistakes is hand-waving the latency budget. "The model runs in
about 100ms and we have 200ms total, so we're fine." This is not a real analysis. Here is
what a real latency budget looks like, broken down per component:

```
LATENCY BUDGET: Search Ranking API — 200ms p99 total
═══════════════════════════════════════════════════════════════

Component                          p50     p95     p99     Notes
─────────────────────────────────────────────────────────────────
Load balancer + TLS termination     2ms     3ms     5ms    Constant overhead
Feature retrieval (Redis, online)   3ms     8ms    15ms    Cache hit rate ~95%
Feature retrieval (DB fallback)    10ms    30ms    50ms    Cache miss → PostgreSQL
  (only p(miss) = 5% of requests)                          weighted average: 4ms
BM25 retrieval (Lucene, 10M docs)   8ms    12ms    18ms    Parallelized across shards
Embedding ANN search (Faiss)       10ms    15ms    22ms    GPU-accelerated index
Candidate re-ranking (LambdaMART)  12ms    18ms    25ms    200 candidates, CPU
Response serialization + JSON       3ms     5ms     8ms    Protobuf is 2x faster
Network (last-mile to client)      15ms    25ms    35ms    Varies by geography
                                   ────────────────────
Total p99 (serial):                                157ms   ← 43ms headroom ✓

BUT: Feature retrieval + BM25 + ANN are parallelizable:
Total p99 (with parallelism):                      130ms   ← 70ms headroom ✓

═══════════════════════════════════════════════════════════════

KEY DECISION POINT: If ANN search takes 150ms (unoptimized):
- Option A: Switch from CPU Faiss to GPU Faiss → ~20ms (7x speedup)
- Option B: Reduce index size by pre-filtering to 1M items per user's
  geography before ANN search → ~35ms
- Option C: Move ANN search to dedicated FPGA hardware → ~8ms (only
  justified at Google/Meta scale where 1% speedup = $10M savings)
- Option D: Drop embedding retrieval entirely, serve BM25-only until
  you can fix the latency → worse ranking, but meets SLA

The correct answer at most companies: Option B first (cheap), then
Option A if still needed (moderate cost), never Option C unless
you're serving 100B+ requests/day.
```

**The key Redis data structure for the online feature store:**

When you look up features for user `user_id=12345` at serving time, what does the Redis
lookup actually look like?

```
Redis key:   user:12345:features
Redis type:  Hash (field-value pairs)
Redis value: {
    "purchase_count_7d":        12,
    "avg_session_duration_sec": 247,
    "days_since_last_login":    1,
    "preferred_category":       "electronics",
    "account_age_days":         583,
    "lifetime_order_value_usd": 1240.50,
    "_computed_at":             "2024-01-15T14:22:00Z"   ← freshness audit field
}

TTL: 86400 seconds (1 day)  ← features expire if not refreshed
Lookup time: HGETALL user:12345:features → 3-5ms typical
```

**The latency failure mode you must always plan for:**

What happens when Redis is down? This is not hypothetical — Redis goes down during
infrastructure maintenance, network partitions, and memory pressure events. If your
serving path crashes when Redis is down, you have taken down your entire ML feature
depending service.

```
SERVING PATH WITH REDIS FALLBACK

  Request arrives
       │
       ▼
  Redis HGETALL user:12345:features
       │
  ┌────▼──────────────────────────────────────────────────┐
  │  Redis responds in < 20ms?                            │
  └────────────────────────────────────────────────────────┘
       │                              │
     YES ✓                         NO (timeout or error)
       │                              │
       ▼                              ▼
  Use Redis features          Fall back to offline store
  → model inference           (BigQuery / DynamoDB batch table)
  → return prediction         Features are up to 24h stale
                              → still run model, note staleness
                              → if offline store also fails:
                                 → use DEFAULT features
                                 (population averages, zeros)
                                 → return degraded prediction
                                 → log: "serving_mode=fallback"
                                 → alert on-call if fallback > 1%

The circuit breaker opens after 5 consecutive Redis timeouts.
It stays open for 30 seconds, then half-opens (1 request tests
Redis health). This prevents a Redis timeout storm from cascading
into a model serving storm.
```

### Common Mistakes — Part 5: Model Serving

```
COMMON MISTAKES IN MODEL SERVING

Mistake 1: Calling the model synchronously without a timeout
Symptom: One slow model inference call (GPU OOM, slow feature fetch) blocks
the entire request thread. p99 latency spikes to 10+ seconds. Other users
experience timeouts even though their own feature fetches are fast.
Fix: Set a hard timeout on model inference: 150ms. If the timeout fires,
catch the exception, log it, and return a degraded response (popular items,
cached prediction from 1 hour ago, rule-based fallback). The degraded response
is always better than a timeout error or hung request.

Mistake 2: Deploying a new model to 100% traffic immediately
Symptom: New model has a subtle bug — predictions for users in certain regions
are wrong. Discovered by customer support 6 hours after full rollout. By then,
millions of affected users have seen bad recommendations.
Fix: Shadow mode (100% old, 0% visible new) → 1% canary (observe for 24 hours,
compare metrics) → 10% → 50% → 100%. At each stage: automated rollback if p99
latency increases >20%, error rate increases >1%, or business metric drops >5%.

Mistake 3: Running both old and new model in A/B test without user-consistent
assignment
Symptom: The same user sees recommendations from model A on one request and
model B on the next request. The A/B test results are statistically meaningless
because you cannot attribute user behavior to a specific model variant.
Fix: Assign experiment groups at the user level, not the request level.
Store the assignment in a fast key-value store: Redis HGET user:12345:experiment
→ "model_v2". Every request from user 12345 always hits model_v2. The
assignment is stable for the duration of the experiment (typically 2+ weeks
for statistical significance).

Mistake 4: Not accounting for model warm-up on cold instances
Symptom: The first few requests to a newly started model server take 10x longer
than steady-state. Users on freshly auto-scaled instances get timeouts.
Root cause: ML models have expensive initialization (loading weights into GPU
memory, JIT compilation of compute graphs). This can take 5-30 seconds for
large models.
Fix: Add a health check endpoint to the model server that returns 200 only after
the model is fully loaded and warmed up. Load balancer health checks should wait
for this endpoint before routing traffic to the instance. Additionally, warm up
the model with a synthetic batch of requests before declaring it ready.
```

### Intern → Staff Progression (Part 5)

| Level | Serving thinking |
|-------|-----------------|
| **Intern** | Deploys model as a Flask API. Does not think about latency or load. |
| **L3** | Knows about online vs batch. Chooses based on "does it need to be real-time?" without analyzing latency budget. |
| **L4** | Measures P99 latency. Identifies bottlenecks (model inference vs feature fetch). Adds caching for hot users. |
| **L5** | Designs deployment with shadow mode and canary. Builds rollback capability. Monitors error rates and latency per model version. |
| **L6** | Defines latency budget explicitly, allocates to each component, quantifies the accuracy/latency tradeoff of model choices, designs A/B testing infrastructure with proper statistical power, ensures the two-models problem (old + new running simultaneously) is handled correctly at the infrastructure level. |

### Brainstorming Questions (Part 5)

**Q: Your recommendation model takes 150ms to run inference. Your API latency requirement is
200ms total. What are your options?**

The first thing to do is profile the 150ms to understand where time is actually spent. Often,
"model inference" includes model loading, feature retrieval, preprocessing, the actual forward
pass, and postprocessing. The actual neural network forward pass might only be 30ms — but feature
retrieval from a slow store adds 100ms. Profile before optimizing.

If the actual inference is the bottleneck, you have several options: model compression (quantize
from float32 to int8, which can give 2-4x speedup with minimal accuracy loss; prune unused
neurons; or distill a large model into a smaller one trained to mimic the large model's output).
GPU inference is another option — moving from CPU to GPU can give 10x+ speedup for neural
networks. Batching requests (process 16 requests simultaneously on GPU, amortizing the overhead)
increases throughput. These can bring 150ms down to 20-30ms.

If none of these options are achievable fast enough, consider whether this use case actually needs
online serving. If recommendations only depend on the user's historical behavior (not current
session), batch serving is the right answer: precompute recommendations nightly, serve from a
key-value store in < 5ms. You give up real-time personalization but gain reliability and
capacity. The hard business question: how much value does real-time personalization add vs
cached personalization? For most content recommendation scenarios, the answer is "not much."

---

**Q: You have deployed a new model. After two days, you notice the new model has higher CTR
(click-through rate) than the old model, but user satisfaction scores are lower. How do you
handle this?**

This is the classic engagement vs satisfaction conflict, and it is one of the most important
signals an ML system can surface. High CTR with low satisfaction usually means the model is
optimizing for clicks but not for the underlying user intent — it is showing content that grabs
attention (rage-bait, misleading thumbnails, sensationalist titles) rather than content the user
actually wants. YouTube has faced this repeatedly.

The immediate action depends on the magnitude. If satisfaction scores are significantly lower
(more than a few percent), roll back to the old model while you investigate. The old model's
lower CTR at higher satisfaction is likely better for the business in the long run — users who
are satisfied stay on the platform; users who are tricked into clicking eventually leave.

The deeper fix is to change what you are optimizing for in training. If you only train on click
signals, you will get a click-maximizing model. You need to incorporate satisfaction signals
(ratings, watch time, "not interested" signals, return visit rate) into the training objective.
This requires a richer feedback loop: not just "did they click?" but "after they clicked, what
happened?" Multi-objective optimization (optimize a weighted combination of CTR and satisfaction
proxy) or constrained optimization (maximize CTR subject to satisfaction > threshold) are the
tools here. This is exactly the kind of L6 thinking that goes beyond "train a model and deploy
it."

---

**Q: Explain how you would run the old model and the new model simultaneously in production
during an A/B test, without doubling your infrastructure costs.**

Running two models simultaneously is a common problem. The naive approach — two separate model
server deployments at 100% capacity each — indeed doubles costs. The smarter approach exploits
the fact that you do not need both models to have full capacity simultaneously.

The standard solution is to run both models on the same model serving infrastructure using
request routing. Your serving layer reads the user's A/B assignment (typically stored in an
experiment assignment service, keyed by user ID) and routes the request to either model A or
model B. Both model variants run as separate deployments, but each deployment is sized for its
traffic share: if 95% of traffic goes to the control model and 5% to the variant, the variant
deployment needs only 5% of the resources of the control deployment. Total resource increase is
~5%, not 100%.

The model server itself (TF Serving, Triton) supports multi-model serving: you load multiple
model versions simultaneously and route requests by model version tag. This is even more
efficient than separate deployments. One fleet of servers hosts both model A and model B;
the routing happens within the server process. The tricky operational part is ensuring that you
are comparing apples to apples — both models must use the same feature version, same serving
infrastructure, and the assignment must be stable per user (user 123 is always in group A, not
randomly re-assigned on each request).

---

## Part 6: The Feedback Loop Problem

### How Loops Form

Imagine you are teaching a student, and the only way you can teach them is by showing them
examples. But the examples you choose to show them depend on what they have learned so far. If
you start by showing them only math examples, they get good at math and bad at everything else.
Their skill profile influences which examples you show, which influences their skill profile,
and so on. This is a feedback loop.

ML systems have the same problem. The model makes predictions (which items to recommend). Users
interact with what the model shows them. Their interactions become training data. The next model
is trained on interactions that the previous model caused. You are not learning from the world —
you are learning from your own choices.

```
THE FEEDBACK LOOP

  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │   Model ──▶ Predictions ──▶ User sees item A        │
  │     ▲            │                │                  │
  │     │            │                ▼                  │
  │     │            │         User clicks A             │
  │     │            │                │                  │
  │     │            ▼                ▼                  │
  │     └──── Training data ◀── Click logged             │
  │           (only item A)                              │
  │                                                      │
  │   Problem: Item B might be better, but we           │
  │   never showed it, so we never learned about it.    │
  │                                                      │
  └─────────────────────────────────────────────────────┘

  This is SURVIVORSHIP BIAS in ML systems.
```

### The Delay Problem

CTR (click-through rate) as a training signal has a fundamental delay: a user must see an item
(impression) and then click it (or not). The click event may come seconds later — or the user
may close their browser and never return. You do not know whether a non-click is a "decided not
to click" or "left before they had a chance to click."

For some labels, the delay is even longer. If you are predicting whether a user will convert
(make a purchase) after seeing an ad, the conversion might happen days later. Training on labels
with long delays means your training data is always stale — you cannot train on events from
yesterday because you do not yet know which of yesterday's impressions will eventually convert.

### Exploration vs Exploitation

The exploitation-exploration dilemma: if you always show the items your model thinks are best
(exploit), you never learn about new items (explore). If you always explore randomly, you give
users bad recommendations all the time.

The practical balance for most production systems: **epsilon-greedy** (serve the best predicted
item with probability 1-ε, serve a random item with probability ε — typically ε = 1-5%).
The random items are your exploration budget. They help you learn which items are undervalued
by your model.

Thompson Sampling is more sophisticated — it naturally balances exploration and exploitation by
sampling from the model's uncertainty estimate. Used in ad systems at Google, Meta, and Microsoft.

### Position Bias

Item at rank 1 gets clicked more than item at rank 5, even if item at rank 5 is more relevant.
This is **position bias**. If you train on click data without accounting for position bias, your
model learns "items that appear at rank 1 are good" rather than "items that are relevant are
good." The model becomes a self-fulfilling prophecy: it ranks items high because they were
previously ranked high, not because they are good.

Fix: position debiasing during training. Common techniques: propensity weighting (give less
weight to clicks on position 1, more weight to clicks on position 10, because a click on position
10 is a stronger signal of true relevance) or inverse propensity scoring.

### Feedback Loop With Actual Numbers: What Narrowing Looks Like

Here is a concrete worked example showing how a feedback loop causes filter bubbles
over successive retraining cycles. These numbers are illustrative but realistic.

```
SCENARIO: Music recommendation system, 10,000 tracks in catalog

Week 1: Initial model (random initialization)
───────────────────────────────────────────────────────
Impressions distributed across catalog:
  Top 100 tracks:   25% of all impressions
  Next 900 tracks:  45% of all impressions
  Remaining 9,000:  30% of all impressions

Clicks (CTR ~4% average):
  Top 100:   4.8% CTR (popular → higher CTR)
  Next 900:  3.9% CTR
  Bottom:    2.1% CTR

Training signal generated: proportional to impressions × CTR

Week 2: Model retrained on week-1 click data
───────────────────────────────────────────────────────
Model has learned: "top 100 tracks generate more clicks"
→ Model promotes top 100 tracks more aggressively

Impressions shift:
  Top 100 tracks:   38% of all impressions (+13%)
  Next 900 tracks:  42% of all impressions
  Remaining 9,000:  20% of all impressions (-10%)

CTR shifts (same underlying quality, just more exposure):
  Top 100:   5.2% CTR (position 1-3 get more clicks due to prominence)
  Next 900:  3.7% CTR
  Bottom:    1.8% CTR  ← DEGRADING: less data, less refinement

Week 6: Model retrained through 5 cycles
───────────────────────────────────────────────────────
Impressions now:
  Top 100 tracks:   65% of all impressions
  Next 900 tracks:  30% of all impressions
  Remaining 9,000:   5% of all impressions ← near zero

CTR shifts:
  Top 100:   5.8% CTR  ← artificially inflated by position effects
  Bottom:    0.9% CTR  ← degraded: users never discover these tracks

Business metric: overall CTR went from 4% to 4.6% → looks like IMPROVEMENT
Reality: 90% of catalog is starved of impressions. Catalog is effectively
         narrowing to 1,000 tracks. User satisfaction (measured by return
         visit rate, playlist additions) has dropped 8%.

The model's aggregate CTR metric went UP while user satisfaction went DOWN.
If you only monitor CTR, you will not notice the filter bubble forming.
```

**The mitigation in numbers:**

```
EPSILON-GREEDY EXPLORATION: epsilon = 5%

In a 20-item recommendation feed:
  19 slots → model's best ranked items (exploitation)
   1 slot  → randomly sampled from full catalog (exploration)

The exploration slot is:
  - Randomly sampled from tracks outside the model's top-200
  - Logged with a flag: "exploration=true"
  - Excluded from standard training (to avoid biasing toward
    random items)
  - Analyzed separately: "of all exploration slots shown,
    what was the CTR by track?" → reveals undervalued tracks

After 6 weeks with exploration:
  Top 100 tracks:   42% of impressions (vs 65% without exploration)
  Next 900 tracks:  44% of impressions
  Bottom 9,000:     14% of impressions (vs 5% without exploration)

The distribution is still skewed (popular content is still popular),
but the feedback loop has not compressed the catalog to 1,000 tracks.
```

### Real Example: YouTube's Recommendation Feedback Loop

YouTube switched from a time-watched signal to a satisfaction survey signal (2019) after
discovering that optimizing for watch time led the recommendation engine to recommend increasingly
sensationalist, anxiety-inducing content. The model had correctly learned that outrage content
keeps people watching — it just turned out that keeping people watching is not the same as keeping
people satisfied or coming back tomorrow. The feedback loop had quietly tuned the model toward
content that was bad for users but good for a narrow engagement metric.

### Intern → Staff Progression (Part 6)

| Level | Feedback loop understanding |
|-------|---------------------------|
| **Intern** | Not aware of the problem. Trains on click data directly. |
| **L3** | Knows feedback loops exist. Does not know how to fix them. |
| **L4** | Adds exploration budget (epsilon-greedy). Logs exploration flag to exclude from training. |
| **L5** | Implements position debiasing. Understands label delay and handles it with time windowing. |
| **L6** | Designs a complete feedback loop management system: counterfactual logging, causal inference for debiasing, multi-objective optimization to balance engagement vs satisfaction, A/B tests to validate that exploration policy improves model quality over time. |

### Brainstorming Questions (Part 6)

**Q: How do you detect that your recommendation system has developed a filter bubble — users
are only being recommended content from a narrow range?**

The signal to monitor is **recommendation diversity** — a metric that measures how varied the
content shown to each user is over time. Concretely: if you look at all the items recommended
to user X over the last 30 days, what percentage of the catalog have they been exposed to?
What is the average pairwise dissimilarity between recommended items (using item embeddings)?
If diversity drops over successive model retraining cycles, the feedback loop is narrowing.

A population-level view is also useful: measure the distribution of impressions across items.
If the Gini coefficient (a measure of inequality) of impressions increases over time — a smaller
and smaller fraction of items getting a larger and larger share of impressions — that is a
filter bubble forming at the system level. Compare this to a baseline of random recommendations
to understand the magnitude of narrowing. Alert when diversity drops more than X% from baseline.

The hardest part is distinguishing between "the model correctly learned that these users want
narrow content" (legitimate personalization) and "the feedback loop is trapping users in a
bubble" (harmful narrowing). The distinction usually requires user research: ask users whether
they feel their recommendations are too repetitive, or compare satisfaction scores between
high-diversity and low-diversity recommendation cohorts.

---

**Q: Your fraud model's training labels are "confirmed fraud" — cases where the fraud team
reviewed and confirmed. But the fraud team can only review 0.1% of flagged transactions.
How does this affect your model, and what do you do about it?**

This is a classic **label selection bias** problem. The model flags some transactions as
suspicious; those flagged transactions get reviewed; the reviewed ones become your labeled
training data. But the un-flagged transactions (which the model said were safe) are never
reviewed. You never know if those were actually fraud cases that the model missed.

The consequence: your model has no learning signal from its false negatives. If your model
is systematically wrong about a new type of fraud — say, it has never seen account takeover
fraud before — it will give those transactions low fraud scores, they will not be reviewed, and
you will have no data showing that they are fraud. The model cannot learn to detect new fraud
patterns that it has never flagged before. This is **survivorship bias** applied to fraud.

The mitigation is to add a **random holdout review**: randomly select 1% of all transactions
(regardless of model score) for human review. This gives you an unbiased sample of the full
population, including cases the model would have missed. It is expensive (you are reviewing
transactions the model thinks are safe, most of which actually are safe), but it is the only
way to detect systematic blind spots. You also implement **counterfactual logging**: record
every case where you almost flagged a transaction but did not, so you can later investigate
whether those were fraud.

---

## Part 7: Monitoring and Drift Detection

### What Drifts and Why It Matters

Your model is a snapshot of the world at the time it was trained. The world keeps changing.
The model does not. Over time, there is an increasing mismatch between "what the model knows"
and "how the world actually is." This mismatch causes predictions to get worse. This is **drift**.

Think of it like a GPS map from 2019. It still routes you correctly to most places. But new
roads are not on it, some streets have changed direction, and some restaurants it suggests are
closed. The map (model) is stale relative to the territory (current world).

```
TYPES OF DRIFT

  DATA DRIFT (input distribution changes)
  
  Feature: "User's daily active minutes on app"
  
  Training data (January):         │  Production (March):
  ─────────────────────────────────│──────────────────────────────
         ████                      │                 ████
       ████████                    │          ██████████████
     ████████████                  │        ████████████████████
   0    30    60    90 min         │  0    30    60    90   120 min
  
  Distribution shifted right (users spending more time on app).
  Model was trained on January distribution → predictions less accurate.
  
  ─────────────────────────────────────────────────────────────────
  
  CONCEPT DRIFT (label relationship changes)
  
  Before COVID:
  "user searched 'hand sanitizer'" → probably health-conscious → churn risk: LOW
  
  After COVID:
  "user searched 'hand sanitizer'" → panic buying → churn risk: HIGH (totally different meaning)
  
  The FEATURE is the same. The LABEL relationship changed.
```

### What to Monitor

At each layer of the ML system:

**Input features:** For each feature, track: mean, standard deviation, null rate, quantile
distributions. Statistical tests to detect shift: KS test (two-sample Kolmogorov-Smirnov),
PSI (Population Stability Index), KL divergence. Alert when a feature's PSI > 0.2 (industry
standard threshold for "significant shift").

**Model outputs:** Track the distribution of predictions. If your fraud model normally predicts
"fraud probability" in the range [0.001, 0.05] for 99% of transactions, and suddenly predictions
cluster around [0.5, 0.9], something has changed. Either inputs changed (data drift) or the
model is broken.

**Business metrics:** The ultimate truth. Track: CTR, conversion rate, fraud loss rate, user
satisfaction, revenue per recommendation. Business metric degradation is the final signal that
your model has gone wrong. The problem: this signal is delayed. You want to catch drift earlier.

**Labels (where available):** If you have real-time label feedback (fraud chargebacks come in
within days), monitor the label rate. If your model normally has a 0.1% fraud rate and it
suddenly jumps to 1%, something has changed.

### The Monitoring Stack

```
DRIFT MONITORING ARCHITECTURE

  Model predictions (real-time)
         │
         ▼
  ┌──────────────────────────────────────────────┐
  │  Feature distribution tracker               │
  │  (compute PSI, KS test every hour)          │
  └───────────────────────┬──────────────────────┘
                          │
              ┌───────────▼────────────┐
              │   Alert Rules Engine   │
              │  PSI > 0.2 → WARN      │
              │  PSI > 0.3 → RETRAIN   │
              │  Prediction dist shift  │
              │  → PAGE ON CALL        │
              └───────────┬────────────┘
                          │
               ┌──────────▼──────────┐
               │   Actions           │
               │  - Notify team      │
               │  - Trigger retrain  │
               │  - Rollback model   │
               │  - Page on-call     │
               └─────────────────────┘
```

### Concrete Drift Detection: PSI Calculation Worked Example

PSI (Population Stability Index) is the industry-standard metric for detecting feature drift.
Here is what it looks like in practice — not just the definition, but actual numbers.

```
FEATURE: user_age_bucket
Purpose: Used in a churn prediction model. Age correlates with subscription tier.

               Training dist.  Production dist.  PSI contribution
               (3 months ago)  (this week)
─────────────────────────────────────────────────────────────────────
age 18-24:         12%              18%         (0.18-0.12)*ln(0.18/0.12) = 0.028
age 25-34:         28%              22%         (0.22-0.28)*ln(0.22/0.28) = 0.018
age 35-44:         31%              25%         (0.25-0.31)*ln(0.25/0.31) = 0.016
age 45-54:         18%              20%         (0.20-0.18)*ln(0.20/0.18) = 0.002
age 55+:           11%              15%         (0.15-0.11)*ln(0.15/0.11) = 0.015
                                                ──────────────────────────────────
PSI total:                                                                   0.079

ALERT THRESHOLD EXCEEDED (0.079 > 0.05)
```

**How to read this:**

```
PSI THRESHOLDS (industry standard)

PSI < 0.05  → NO significant drift. Model is stable. Continue monitoring.
PSI 0.05–0.10 → MINOR drift. Monitor closely. Begin investigating cause.
PSI 0.10–0.25 → MODERATE drift. Model may be degraded. Consider retraining.
PSI > 0.25  → SEVERE drift. Model is likely producing bad predictions.
               Trigger immediate retraining. Consider fallback.

In our example: PSI = 0.079 → MINOR drift.
Action: Flag for investigation. Check if it is seasonal (summer vs fall age
cohort patterns?), or if a marketing campaign targeted a specific age group,
or if the product changed in a way that attracts/repels certain ages.
Do NOT trigger immediate retraining — wait for more data or for PSI to exceed 0.10.
```

**What to do with this in the interview:**

When asked about drift detection, do not just say "use PSI." Say: "I would compute PSI
per feature, using the training distribution as the reference distribution and the last
7-day production distribution as the comparison. I would run this calculation hourly for
high-volatility features like user activity counts, and daily for stable features like
demographics. Alert at PSI > 0.10, trigger retraining at PSI > 0.25. Log the PSI
history per feature so I can see trends — is drift increasing steadily (suggests a slow
world change) or did it jump suddenly (suggests a data pipeline bug or product event)?"

**A concrete worked example of concept drift vs data drift:**

```
SCENARIO: E-commerce recommendation model, January → March

Feature: "user_search_query_count_7d" (searches per week)

DATA DRIFT (input distribution changed):
  January avg: 8.2 searches/week
  March avg:   14.6 searches/week
  
  Cause: Marketing campaign launched Feb 15, drove 80% more site traffic.
  PSI = 0.31 → SEVERE drift.
  
  What happens to the model: It was trained on users with ~8 searches/week
  as the norm. It now sees users with ~15 searches/week as "typical."
  Its behavior for high-search users (who it used to consider power users)
  changes because that behavior now describes average users.
  
  Fix: Retrain on data from post-campaign period. Feature normalization may
  also help (normalize to z-score so the model sees "this user is 1.5 std
  above mean" regardless of what the mean is).

CONCEPT DRIFT (label relationship changed, input distribution same):
  Feature: "user_search_query_count_7d" — SAME distribution Jan and Mar.
  
  But in January: high search count → user is engaged → low churn risk
  In March: high search count → user can't find what they want → HIGH churn risk
  
  (Cause: A product change made search less effective. Users searching more
  because they are frustrated, not because they are engaged.)
  
  PSI = 0.02 → NO drift detected by feature monitoring!
  But model accuracy dropped 18% because the label relationship flipped.
  
  How to detect concept drift (not caught by PSI):
  → Monitor actual label rates: churn rate among high-search-count users
    went from 3% to 19%. That's your signal.
  → Requires ground-truth label availability (delayed by 30 days for churn).
  → For faster detection: monitor a leading indicator (support ticket rate
    from high-search users is a 7-day leading indicator of churn).
```

### Real Example: Slack and COVID-19 (2020)

When COVID-19 hit in March 2020, Slack's usage exploded overnight as the entire workforce went
remote. Every behavioral signal changed simultaneously: message volume, channel activity patterns,
peak usage hours, types of content, device distribution. ML models trained on pre-COVID Slack
behavior — used for things like smart notifications, channel recommendations, and search ranking
— all degraded at once. The models were trained on a world where most people used Slack from
9-5 on weekdays; suddenly people were using it at all hours from personal devices.

The lesson: monitoring must catch population-level shifts before users notice. Slack did not have
robust drift detection in place at the time. Users and customer success reported degraded
experiences before the ML team identified that their models needed retraining. Post-COVID, the
industry has invested significantly in drift detection tooling.

### Common Mistakes — Part 7: Monitoring and Drift Detection

```
COMMON MISTAKES IN ML MONITORING

Mistake 1: Only monitoring business metrics, not feature/prediction distributions
Symptom: A feature pipeline bug corrupts the "purchase_count_7d" feature for
3 hours. The model produces bad predictions for those 3 hours. Business metrics
(CTR, conversion) dip slightly but not enough to trigger an alert (business
metrics have high variance). The bug is discovered 2 days later by a data
scientist who notices the feature looks wrong in the offline store.
Fix: Monitor feature distributions in REAL TIME. If the mean of
"purchase_count_7d" drops by 50% in one hour, that is a pipeline bug, not
user behavior change. Alert immediately, before it affects business metrics.

Mistake 2: Monitoring each feature independently (univariate), missing
correlated multi-feature shifts
Symptom: COVID-19 hits. Every feature shifts simultaneously. Each individual
feature's PSI is below threshold (a 5% shift in one feature is minor). But
50 features shifting 5% at the same time is a major event. Univariate
monitoring misses it.
Fix: Add a multivariate drift detector: compute the Mahalanobis distance
between today's feature distribution and the training distribution, accounting
for feature correlations. A large Mahalanobis distance catches correlated
multi-feature shifts even when each individual PSI is low.

Mistake 3: Same alert threshold for all features
Symptom: "User's age" triggers a drift alert because 0.5% more 18-24 year-olds
signed up this week. This is noise. Meanwhile, "card transaction velocity" has
genuine fraud-pattern drift but the threshold is set too high, so it doesn't
alert until the model is already wrong for 6 hours.
Fix: Set per-feature thresholds based on that feature's historical variance.
A feature with high natural variance (session count) needs a higher PSI
threshold than a stable feature (user age bucket). Use your last 90 days of
monitoring data to calibrate what "normal variance" looks like per feature.

Mistake 4: Not having a runbook for drift alerts
Symptom: PagerDuty fires at 3am: "PSI for feature X exceeded 0.25." The
on-call engineer has never seen an ML drift alert before. They do not know
what to do. They acknowledge the alert and go back to sleep.
Fix: Write a runbook for every alert type:
  → Is this a data pipeline bug (fast fix) or genuine world drift (needs retrain)?
  → How do I check? (Link to the feature distribution dashboard)
  → What is the immediate mitigation? (Roll back to last known good model,
     or activate rule-based fallback)
  → Who is the escalation contact if it's a pipeline bug?
  The runbook is as important as the alert itself.
```

### Intern → Staff Progression (Part 7)

| Level | Monitoring approach |
|-------|---------------------|
| **Intern** | No monitoring. Finds out model is bad when users complain. |
| **L3** | Adds basic accuracy logging. Checks it manually once a week. |
| **L4** | Sets up automated alerts on business metrics (CTR, conversion). Still reactive. |
| **L5** | Adds feature distribution monitoring with automated PSI calculation. Sets up retraining triggers. |
| **L6** | Designs a full observability system: feature drift per feature with severity tiers, prediction distribution monitoring, upstream data quality checks, automatic root cause analysis (is drift in feature X causing the prediction shift?), automatic retraining with validation gates before promotion, and a runbook for on-call response to drift alerts. |

### Brainstorming Questions (Part 7)

**Q: Your model monitoring shows that feature PSI is within normal range, but business metrics
have degraded significantly. What are the possible causes?**

This is a classic case where the monitoring that should have caught the problem did not. The
features look normal, but the model's real-world performance is bad. The most likely explanation
is **concept drift without data drift**: the inputs have not changed, but the relationship
between inputs and the correct label has changed. Your feature for "number of purchases in last
30 days = 5" used to correlate strongly with "loyal customer" (low churn risk). But suppose
the product introduced a new discount program that triggered a one-time purchase spike — now
5 purchases in 30 days does not mean loyalty, it means deal-seeking behavior. The feature value
is normal; its meaning changed.

Another possibility is that the **label distribution changed** but you are only monitoring
features and predictions, not labels. If the actual churn rate doubled (because a competitor
launched a product), your model might still be outputting its normal distribution of churn scores
— it does not know about the competitor. The features are normal, the predictions are normal, but
the model is now systematically wrong because the underlying reality changed. Monitoring true
labels (where available) would have caught this.

A third cause is a change **outside the ML system** that the model cannot see: a new product UI
that changes how users interact with the feature being predicted, a marketing campaign that
changes user intent, a change in how events are logged that corrupts the signal upstream of the
feature pipeline. The model is fine; the world around it changed in a way that makes its
predictions irrelevant. This is why end-to-end business metric monitoring is mandatory even when
feature and prediction monitoring look clean.

---

**Q: You get a page at 3am saying "model accuracy dropped 40%." Walk me through your
on-call response.**

The first question is: what does "model accuracy dropped 40%" mean exactly? Is this absolute
accuracy (was 90%, now 54%) or relative (was 90%, now 86%, a 4 percentage point drop reported
as "40% of our error budget gone")? Confirm the metric definition. Check if the alert is a
monitoring bug (wrong baseline, wrong data), a temporary blip, or a real sustained degradation
by looking at the trend over the last few hours.

If the degradation is real, check the obvious causes first: was there a model deployment in the
last 12 hours? Roll it back if so — this is the fastest fix and restores service while you
investigate. Was there a data pipeline failure that caused features to be wrong or missing?
Check the feature pipeline dashboards. Null features or features with wrong values will cause
catastrophic prediction errors immediately. Was there an upstream data schema change? Check
the schema registry and recent changes to event schemas.

If none of the obvious causes apply, dig into the feature distribution dashboard: which features
shifted? Is the shift correlated with a specific user segment, device type, or geographic region?
This helps you narrow down whether it is a product change (new app version changed event
logging), an infrastructure change (a database that feeds features had a schema migration), or
a genuine world event (a news story changed user behavior overnight). Document everything you
find, even if you do not solve it before handing off to the morning shift. In parallel, consider
switching to a rule-based fallback if the model is completely broken and serving bad predictions
is causing real harm.

---

### Real Incident (Part 7): Slack and the COVID-19 Overnight Drift

In March 2020, the US declared a national emergency over COVID-19 on a Friday afternoon. By Monday, a substantial fraction of the global office workforce was working from home full-time, using Slack all day on personal devices instead of occasionally in an office. What had been a gradual, slow-moving signal — Slack usage trends — became a near-instantaneous step-change across virtually every feature that Slack's ML models depended on. Message volume spiked. Usage hours expanded from a clean 9-5 weekday window to 24-7. New channels with no historical analog (#remote-work-tips, #covid-resources, #home-office-setup) became massively active overnight. Device distribution shifted as people moved from managed corporate laptops to personal machines and phones.

Every ML model Slack had trained on pre-COVID behavior broke at the same time. The notification intelligence model (which learned when to interrupt you vs. let messages queue) was calibrated to a world where you were at your desk and a notification at 11am was useful. Now people were in different time zones, on different schedules, with children home from school — and the same features that used to predict "good time to notify" now predicted wrong. The channel recommendation model surfaced channels based on what similar users engaged with; but "similar users" clusters had all been learned on pre-COVID behavior patterns and bore no resemblance to the new usage. Search ranking surfaced messages based on recency and engagement signals that had all been recalibrated to a normal world.

The key failure was in the monitoring architecture. Slack's drift detection at the time was primarily reactive: business and customer success teams noticed degraded experiences and filed reports before the ML team diagnosed that model retraining was the root cause. The models themselves had no automated drift alerts that would have fired on simultaneous multi-feature distribution shifts. This is a known limitation of univariate feature monitoring (checking each feature independently) — it misses correlated shifts where many features move together. A multivariate monitoring system that computes a joint distribution shift statistic (like the Mahalanobis distance across all features simultaneously) would have detected the COVID shock much earlier, because the shock was characterized precisely by all features moving at once in the same direction. Post-COVID, the engineering industry invested heavily in exactly this kind of multivariate drift detection, and in "black swan playbooks" that define: when a major external event happens, how quickly can we retrain all models, what is the safe deployment sequence, and what rule-based fallbacks do we activate while retraining is in progress?

---

## Part 8: Common ML System Interview Patterns

The same four system types appear in L6 interviews repeatedly. Here is how to answer each one
at depth.

### Pattern 1: Recommendation System

**The two-stage architecture** (and why it exists):

The core problem: you have 50 million items and 200ms to decide which 10 to show a user. Running
your full ranking model on 50 million items is not feasible — even at 1ms per item, that is 50,000
seconds. The solution: two stages with very different performance characteristics.

```
RECOMMENDATION SYSTEM: TWO-STAGE ARCHITECTURE

  User Request
       │
       ▼
  ┌────────────────────────────────────────────────────┐
  │  STAGE 1: RETRIEVAL (fast, imprecise)              │
  │                                                    │
  │  Goal: 50M items → ~500 candidates                 │
  │  Method: approximate nearest neighbor search       │
  │          in embedding space (Faiss, ScaNN)         │
  │  Time budget: ~20ms                                │
  │  Features: simple (user embedding, item embedding) │
  └────────────────────────┬───────────────────────────┘
                           │ ~500 candidates
                           ▼
  ┌────────────────────────────────────────────────────┐
  │  STAGE 2: RANKING (slow, precise)                  │
  │                                                    │
  │  Goal: 500 candidates → 10 final recommendations   │
  │  Method: full feature-rich ranking model           │
  │          (gradient boosted trees, deep model)      │
  │  Time budget: ~100ms for 500 items                 │
  │  Features: rich (user-item interaction history,    │
  │            context, freshness, diversity signals)  │
  └────────────────────────┬───────────────────────────┘
                           │ 10 results
                           ▼
                      User sees 10 recommendations
```

**Cold start problem:** New users have no history. New items have no engagement data. Options:
- New users: ask onboarding questions (demographics, interests) to build an initial profile;
  fall back to popularity-based recommendations; use demographic similarity to similar users.
- New items: use content-based features (item description, category, metadata); bootstrap with
  human-curated placements; explore aggressively (show new items to some users to gather data).

### What This Looks Like in the Interview: Recommendation System (YouTube)

The interviewer says: **"Design a recommendation system for YouTube."**

Here is what an L6 candidate says and draws from minute 0 to minute 20.

---

**Minutes 0-3: Clarification (Do NOT skip this)**

"Before I design anything, I want to clarify a few things.

First — which recommendations specifically? The homepage feed, the 'Up Next' sidebar while
watching a video, or search results? They have different contexts and constraints.
I'll assume homepage feed, but let me know if you want a different surface.

Second — what scale? YouTube has ~2 billion logged-in users per month and ~800 million videos.
I'll design for that scale, but let me know if we're talking about a smaller platform.

Third — what does success look like? Click-through rate? Watch time? User satisfaction?
This matters because different objectives lead to very different model designs.
I'll assume we want to maximize long-term user satisfaction, proxied by watch time and return
visit rate — NOT just CTR, because CTR-optimized systems tend toward clickbait."

---

**Minutes 3-5: North Star Statement**

"Here is my frame before I draw anything. A recommendation system at YouTube scale has three
constraints that completely dominate the design:

Constraint 1: **Scale.** 800 million videos. You cannot score all of them for every user.
You need a two-stage architecture: first narrow down to a few hundred candidates fast, then
rank those candidates precisely.

Constraint 2: **Latency.** The homepage must load in under 200ms. The model inference must
fit inside that budget along with feature retrieval and everything else.

Constraint 3: **Feedback loop.** Whatever you optimize for, the model will change user behavior,
and that changed behavior will become your training data. If you optimize for watch time, users
will watch more anxiety-inducing content that they cannot stop watching. You need explicit
feedback loop management.

With those three constraints in mind, here is the architecture I will design."

---

**Minutes 5-10: Draw the Two-Stage Architecture**

*[Candidate draws this on the whiteboard — replicated here as text]*

```
USER REQUEST (opens YouTube homepage)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  STAGE 1: CANDIDATE RETRIEVAL  (~20ms budget)                │
│                                                               │
│  Input:  User embedding vector (512-dim, from user history)  │
│  Method: Approximate Nearest Neighbor search (ScaNN/Faiss)   │
│  Index:  Video embeddings pre-computed offline, 800M items    │
│          indexed in ScaNN, stored on dedicated retrieval fleet│
│                                                               │
│  Also retrieve from:                                          │
│    - User's subscribed channels (deterministic, no ML)        │
│    - Trending in user's region (popularity signal)            │
│    - Previously watched creator (pattern matching)            │
│                                                               │
│  Output: ~500 candidate videos                                │
└──────────────────────────────────┬───────────────────────────┘
                                   │ 500 candidates
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│  STAGE 2: RANKING  (~80ms budget)                             │
│                                                               │
│  Input:  500 candidates + rich features per candidate         │
│  Features:                                                    │
│    User features: watch history, search history, location     │
│    Video features: age, category, creator, historical CTR     │
│    Context features: time of day, device, session length      │
│    Cross features: "did user previously watch this creator?"  │
│                                                               │
│  Model: Deep neural network (Wide & Deep or Two-Tower)        │
│  Output: Ranked list → top 20 videos to display               │
│                                                               │
│  Post-ranking filters:                                        │
│    - Diversity: no more than 3 videos per creator             │
│    - Freshness: min 10% of recommendations from last 7 days   │
│    - Safety: exclude flagged content                          │
└──────────────────────────────────┬───────────────────────────┘
                                   │ 20 final recommendations
                                   ▼
                             User sees feed
```

---

**Minutes 10-15: The Key Trade-off (L6 depth signal)**

"I want to explain WHY two stages instead of one, because this is the insight that separates
a surface-level answer from a real design.

If I had one stage — a single model that scored all 800 million videos — I would need to run
800 million inference calls per user request. Even at 0.01ms per call, that is 8,000 seconds.
Clearly impossible within a 200ms budget.

So the two stages exist for different reasons:

**Stage 1 (retrieval) is optimized for speed, not precision.** It uses simple math (vector
dot product in embedding space), precomputed indexes, and fast approximate algorithms. It
will make some mistakes — it will include some irrelevant candidates and miss some great ones.
That is fine. Its job is just to narrow 800 million down to 500.

**Stage 2 (ranking) is optimized for precision, not speed.** It uses a rich feature set —
user-video interaction history, context, cross-features — that would be too expensive to
compute for 800 million items. But for 500 items, it is fast enough. It makes the final
call on which 20 items to show.

The reason most candidates miss this: they either propose one stage (not scalable) or they
propose two stages without explaining the asymmetry in what each stage is optimizing for
and why. The asymmetry — fast+imprecise first, slow+precise second — is the core insight."

---

**Minutes 15-20: Surfaces the Feedback Loop Risk (proactively)**

"Before we move to data pipeline and monitoring, I want to flag a risk I see in this design,
because I think it is more important than any individual component.

The feedback loop: Stage 2 ranks videos. Users click what they see. Those clicks become
training labels for the next Stage 2 model. Items that never appear in Stage 2 never get
clicked, so the next model has no signal about them. Over time, the model becomes increasingly
confident about videos it has already promoted, and less able to discover that videos it has
not promoted might be better.

The specific consequence for YouTube: popular creators get more impressions, more clicks, more
training signal, and the next model ranks them even higher. New creators get fewer impressions,
fewer clicks, less training signal, and the next model ranks them even lower. Over 6 months,
the model creates a rich-get-richer dynamic where the top 1% of creators capture an increasing
share of all impressions.

The mitigations I would design:

First, an exploration budget: 5% of Stage 2 slots are reserved for 'exploration' — randomly
sampled videos from the retrieval pool that Stage 2 would not have ranked in the top 20. These
slots are logged separately and provide unbiased signal about underranked content.

Second, position debiasing in training: clicks at rank 1 are downweighted relative to clicks at
rank 15. A click on a video you placed at rank 15 is a stronger signal of true relevance than
a click on a video you placed at rank 1.

Third, a watch-time floor: even if a video has low CTR (people don't click it much), if users
who do click it watch 80% of the video, that is a strong satisfaction signal. Mix watch
completion rate into the training objective, not just raw CTR."

---

**Likely interviewer follow-up: "How do you handle cold start for new videos?"**

"Two-part answer.

For new videos from established creators: the video's embedding is initialized from the creator's
channel embedding (we already know what the creator's audience looks like). The retrieval stage
can surface it based on creator channel affinity, even with zero watch data on the new video itself.

For new videos from new creators: the video is initially in a 'cold start' pool. We use
content-based features — video title, description, tags, category — to compute an initial
embedding from a text model. We route it to a small random exploration slice (0.1% of users
who appear interested in that category based on watch history). After it accumulates 100 views,
we have enough behavioral signal to compute a real embedding and graduate it to the main pool.

The cold start pool is separate from the main recommendation pool. New creator content is never
competing directly with proven content during its cold start period — that battle is rigged
against new creators. The cold start pool has separate retrieval and ranking models, trained
specifically to maximize diversity and discovery. Once a video proves itself in the cold start
pool, it enters the main pool."

---

**The one L6 signal moment:**

"The thing most candidates miss on recommendation system design is the **feedback loop
asymmetry**: the model decides what to show, which determines what gets clicked, which
determines what the next model learns. This is not a monitoring problem — you cannot alert
your way out of it. It must be designed out of the system through exploration policies,
position debiasing, and training signal diversity. If you do not address it explicitly,
the model will quietly converge to a less diverse, less fair set of recommendations over
time, and your aggregate business metrics (total engagement) might even look fine while
the harm to creator diversity is happening. This is why I always address the feedback loop
before we finalize any other design choice."

#### Intern → Staff Progression (Recommendation System)

| Level | How they design the recommendation system |
|-------|------------------------------------------|
| **Intern** | Suggests collaborative filtering. Returns top-N most popular items as fallback for new users. Does not think about how you rank 50M items in 200ms. |
| **L3** | Knows about two-stage retrieval-ranking. Proposes embedding-based retrieval without knowing what ANN index to use or how to build the embeddings. |
| **L4** | Proposes Faiss or ScaNN for approximate nearest neighbor retrieval. Knows the ranking model should be feature-rich. Addresses cold start with content-based fallback. Still treats the feedback loop as someone else's problem. |
| **L5** | Designs the full two-stage pipeline with latency budgets per stage (~20ms retrieval, ~100ms ranking). Addresses the feedback loop by adding an exploration budget. Designs the training data pipeline: how do you generate labeled pairs (user, item, clicked/not-clicked)? |
| **L6** | Adds position debiasing to the ranking model training (clicks at rank 1 are not the same as clicks at rank 5). Designs multi-objective ranking (not just CTR, but also diversity and freshness). Proposes how to A/B test retrieval vs ranking changes independently. Thinks about the long-term health of the feedback loop: are certain content types being starved of impressions because the model never retrieves them? |

#### Real Incident (Recommendation System): Netflix Prize Winner Not Deployed

Netflix ran a public contest from 2006 to 2009, offering $1 million to anyone who could improve their recommendation accuracy by 10% over their existing system. The winning team — an ensemble called "BellKor's Pragmatic Chaos" — achieved the required improvement and collected the prize. The winning solution blended 107 different models together, combining their predictions in a weighted ensemble.

Netflix never deployed the winning model to production. The engineering team evaluated it against their serving infrastructure and found two problems. First, the ensemble was too slow: running 107 models and combining their outputs took significantly longer than their latency budget allowed. With millions of users opening the Netflix app expecting recommendations to appear instantly, a slow recommendation system is not better — it is unusable. Second, and more importantly, Netflix's product had changed dramatically between 2006 (when the contest data was collected) and 2009 (when the contest ended). The contest data was based on DVD rental history. Netflix had pivoted to streaming. The behavioral patterns, content catalog, and user intent behind a DVD rental are fundamentally different from streaming. The winning model had been optimized for a problem that no longer existed.

The lesson for ML system design interviews is explicit: you cannot optimize a model in isolation from its serving constraints. A model that takes 5 seconds to run and your latency requirement is 200ms is not a good model — it is an undeployable model, regardless of its accuracy. This incident is cited constantly in ML engineering to justify why the serving infrastructure design must happen in parallel with model design, not after. The best model you can actually serve is always better than the most accurate model that sits on a shelf.

---

### Pattern 2: Fraud Detection

**The core constraints:**
- Decision must happen before the transaction completes: < 300ms end-to-end
- False positive rate must be < 0.1% (wrongly declining legitimate transactions is costly)
- Class imbalance: 99.99% of transactions are legitimate

```
FRAUD DETECTION ARCHITECTURE

  Transaction Request
         │
         ▼
  ┌─────────────────┐
  │  RULE ENGINE    │  ← Fast. Blocks obvious fraud.
  │  (synchronous,  │    e.g., "amount > $10,000 AND
  │   < 10ms)       │    card issued < 1 week ago"
  └────────┬────────┘
           │ passed rules
           ▼
  ┌─────────────────────────────────────────────────────┐
  │  FEATURE COMPUTATION (real-time, < 50ms)            │
  │                                                     │
  │  Velocity features:                                 │
  │    - # transactions in last 1hr / 24hr / 7days      │
  │    - total $ in last 1hr                            │
  │  Graph features (from streaming):                   │
  │    - is card linked to known fraud accounts?        │
  │  Device fingerprint:                                │
  │    - is device new? unusual browser config?         │
  └─────────────────────┬───────────────────────────────┘
                        │ features computed
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  ML MODEL (< 50ms)                                  │
  │  Gradient boosted trees (XGBoost/LightGBM)          │
  │  Output: fraud probability score [0, 1]             │
  └─────────────────────┬───────────────────────────────┘
                        │ score
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  DECISION LOGIC                                     │
  │  Score < 0.3  → APPROVE                             │
  │  Score 0.3-0.7→ STEP-UP AUTH (extra verification)  │
  │  Score > 0.7  → DECLINE or HUMAN REVIEW             │
  └─────────────────────────────────────────────────────┘
```

**The asymmetry problem:** A model that always says "not fraud" is 99.99% accurate. Accuracy
is the wrong metric. Use: precision and recall at your operating threshold, F1 score, or AUC-ROC.
The business metric is: (fraud loss prevented) vs (revenue lost from declined legitimate
transactions). Tune the threshold to maximize this business value, not accuracy.

**Velocity features require streaming:** "Number of transactions in the last 1 hour" cannot be
precomputed in batch. It changes every second. You need a streaming aggregation system (Kafka +
Flink with stateful sliding windows) that maintains up-to-the-second counters per card.

### What This Looks Like in the Interview: Fraud Detection System

The interviewer says: **"Design a real-time fraud detection system for a payment processor
handling 10,000 transactions per second."**

---

**Minutes 0-3: Clarification**

"A few questions before I design.

First — what kind of fraud? Card-not-present fraud (stolen card used online)? Account
takeover (attacker gains access to a real account)? New account fraud (fake accounts made
to commit fraud)? Each has different feature sets and detection approaches. I'll design for
card fraud (stolen card used for unauthorized purchases), which is the most common case.

Second — latency requirement? You said real-time. How real-time? Does the transaction have
to be approved or declined before it completes, or can we do post-authorization review?
I'll assume pre-authorization: we need a decision before the transaction is submitted to
the card network. That means under 300ms end-to-end.

Third — what is the cost asymmetry? Approving a fraudulent transaction loses money.
Declining a legitimate transaction loses a customer and revenue. At most processors, a
0.1% false positive rate (wrongly declining 1 in 1,000 real transactions) is the maximum
acceptable. False negatives (approving fraud) are measured in dollars of fraud loss."

---

**Minutes 3-5: Frame the core design constraint**

"The single hardest thing about fraud detection as an ML system — as opposed to, say,
recommendation — is that the decision must be made in real time, the labels are delayed
by days to weeks (chargeback confirmation), and the class imbalance is extreme (fraud is
0.01% of transactions).

These three constraints force specific design choices:
- Real-time decision → online serving only, no batch. Model must be in memory.
- Delayed labels → careful training data construction (you cannot train on today's data
  because you do not know yet which transactions will be disputed)
- Class imbalance → do NOT evaluate by accuracy. Use precision/recall at threshold,
  or ROC-AUC. 'Always predict not-fraud' achieves 99.99% accuracy and is useless.

With those constraints established, here is the architecture."

---

**Minutes 5-12: Draw the architecture**

*[Candidate draws this on the whiteboard]*

```
INCOMING TRANSACTION (10,000/sec peak)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 1: RULE ENGINE  (< 5ms)                               │
│                                                               │
│  Hard rules that block obviously fraudulent transactions:     │
│  - Card blocked by issuer → DECLINE immediately               │
│  - Transaction country on high-risk list + amount > $5,000    │
│    → DECLINE immediately                                      │
│  - Card used at 3+ distinct merchants in last 5 minutes       │
│    → DECLINE (velocity anomaly)                               │
│                                                               │
│  Rules are fast, deterministic, and easy to audit.           │
│  They handle ~15% of fraud cases with no ML needed.          │
│  They also protect the system if the ML model fails.          │
└──────────────────────────────────┬───────────────────────────┘
                                   │ passes rules (~85% of transactions)
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 2: REAL-TIME FEATURE COMPUTATION  (< 30ms)            │
│                                                               │
│  Velocity features (from Redis, updated via Kafka/Flink):     │
│    - txn_count_1h:     # transactions by this card in 1 hr    │
│    - txn_amount_1h:    total $ by this card in 1 hr           │
│    - distinct_merch_24h: # distinct merchants in 24 hrs       │
│    - cross_border_flag: card used in 2+ countries in 24 hrs   │
│                                                               │
│  Redis key structure:                                         │
│    "fraud:velocity:card:{card_token}" → Hash:                 │
│      { txn_count_1h: 3, txn_amount_1h: 247.50,               │
│        distinct_merch_24h: 5, cross_border_flag: 0 }          │
│    Updated by a Flink job consuming Kafka transaction events.  │
│                                                               │
│  User behavioral features (from offline store, BigQuery):     │
│    - avg_txn_amount_90d: user's typical transaction amount    │
│    - preferred_merchant_categories: electronics, groceries    │
│    - account_age_days: how old is this account                │
│                                                               │
│  Transaction context features (from the transaction itself):  │
│    - merchant_category_code (MCC)                             │
│    - transaction_amount                                        │
│    - device_fingerprint_hash                                  │
│    - billing_address matches shipping_address?                │
└──────────────────────────────────┬───────────────────────────┘
                                   │ feature vector ready
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 3: ML MODEL  (< 30ms)                                  │
│                                                               │
│  Model: XGBoost gradient boosted trees                        │
│  Why XGBoost (not deep learning):                             │
│  - Handles tabular features well (velocity counts, amounts)   │
│  - Interpretable: feature importances, decision paths         │
│  - Fast inference: < 10ms for a 100-tree ensemble             │
│  - Robust to outliers (fraud amounts vary wildly)             │
│                                                               │
│  Output: fraud_score ∈ [0.0, 1.0]                            │
│                                                               │
│  Evaluation metric: AUC-ROC (not accuracy)                    │
│  Training data: 90 days of confirmed transactions             │
│  Retrain: weekly (fraud patterns change weekly)               │
└──────────────────────────────────┬───────────────────────────┘
                                   │ fraud_score
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 4: DECISION LOGIC                                      │
│                                                               │
│  fraud_score < 0.20  → APPROVE (low risk)                    │
│  fraud_score 0.20-0.50 → STEP-UP AUTH                        │
│                         (send OTP to phone, ask for CVV)      │
│  fraud_score 0.50-0.80 → HUMAN REVIEW QUEUE                  │
│                         (for high-value transactions)         │
│                         DECLINE for low-value transactions    │
│  fraud_score > 0.80  → DECLINE immediately                   │
│                                                               │
│  The threshold (0.20, 0.50, 0.80) is a business decision,    │
│  not an ML decision. It is tuned to hit target false positive │
│  rate (< 0.1%) while maximizing fraud detection.              │
└──────────────────────────────────────────────────────────────┘
```

---

**Minutes 12-17: The L6 signal — survivorship bias**

"I want to flag the single biggest ML problem specific to fraud detection, because it is
not obvious unless you have built one before.

The model learns from labeled transactions. But which transactions get labeled? Only the
ones where fraud was confirmed — usually by chargeback (the customer disputes the charge).
The model learns: 'transactions with these patterns get disputed.' But if the model is
systematically wrong about a new fraud pattern — say, a new type of social engineering
attack we have never seen before — those transactions score low, they get approved, the
customer's bank eats the loss (not us), and no chargeback comes back to us. We never
learn that we missed them.

This is survivorship bias: the model can only improve on fraud types it has already flagged.
Systematic blind spots are invisible.

The mitigation I would build:

**Random holdout review:** Route 0.3% of all approved transactions (fraud_score < 0.20)
to a human fraud analyst team for manual review. This gives us an unbiased sample of
low-scored transactions. If we find fraud in this sample that our model missed, we have
discovered a blind spot. We add those to the training data and retrain.

This sounds expensive — reviewing 0.3% of 10,000 TPS = 30 transactions per second that
analysts must review. The answer is that this is a prioritized sample: we do not review
30/sec manually, we use a secondary lightweight model to prioritize within this 0.3% sample,
and analysts review the top 100/day from that prioritized sample. The rest go into a log that
is batch-reviewed weekly using pattern analysis to detect emerging fraud types."

---

**Minutes 17-20: Adversarial nature of fraud**

"One more thing that makes fraud unique among ML problems: the adversary adapts.

In a recommendation system, the inputs (user behavior) are not actively trying to fool the
model. In fraud, they are. A sophisticated fraud ring will probe the system: send 100 test
transactions at various amounts and merchants, observe which ones are declined, and then
calibrate their fraud transactions to score just below the decline threshold.

This has two design implications.

First, the model must be partially opaque to the adversary. If the adversary knows exactly
which features drive the fraud score, they can engineer around them. Do not expose the fraud
score to external parties. Decline reasons should be generic ('transaction declined by
issuer'), not specific ('velocity count exceeded threshold').

Second, the model must retrain frequently enough that adversaries cannot map the system.
Weekly retraining changes the model behavior fast enough that a map built 2 weeks ago is
stale. This is why fraud detection is one of the few places where faster retraining directly
improves security, not just accuracy."

---

**The L6 signal moment:**

"The thing most candidates miss on fraud detection is **the feedback loop asymmetry** combined
with **adversarial dynamics**. Most ML systems have a benign feedback loop — user behavior
changes slowly and naturally. Fraud has a hostile feedback loop: the better your model gets,
the more adversaries adapt to evade it. This means fraud ML is never a 'train once and monitor'
problem. It is a continuous arms race that requires monthly or weekly retraining, active
anomaly detection for new fraud patterns, and random holdout sampling to find blind spots
before the adversary exploits them at scale."

#### Intern → Staff Progression (Fraud Detection)

| Level | How they design the fraud detection system |
|-------|------------------------------------------|
| **Intern** | Trains a binary classifier (fraud / not fraud) on transaction history. Does not think about the < 300ms constraint or what happens when the model is down. |
| **L3** | Adds a rule engine layer for obvious cases ("block all transactions over $10,000 to a new account"). Still treats velocity features (transactions in last hour) as a batch computation problem. |
| **L4** | Realizes velocity features require real-time streaming aggregation, not batch. Proposes Kafka + Flink for sliding window counts. Understands class imbalance and knows to use AUC-ROC instead of accuracy as the evaluation metric. |
| **L5** | Designs the full pipeline: rule engine → real-time feature computation → ML model → decision tier (approve/step-up auth/decline). Adds a human review queue for borderline high-value transactions. Designs the retraining pipeline with confirmed fraud labels as ground truth. |
| **L6** | Addresses the survivorship bias problem: the model only gets labels for transactions it flagged, creating blind spots for fraud patterns it has never seen. Adds random holdout reviews (sample 0.5% of all approved transactions for human review) to discover false negatives. Designs graph-based features for card-to-account linkage stored in a graph database. Thinks about the adversarial nature of fraud: fraudsters learn from model behavior and change their patterns, requiring continuous monitoring for new fraud types. |

#### Real Incident (Fraud Detection): PayPal's False Positive Surge During Major Events

Major public events — Black Friday, Cyber Monday, large sports events, celebrity product launches — create sudden, legitimate spikes in purchase behavior that look unusual to fraud models. A user who normally makes 2-3 purchases per week suddenly makes 15 transactions in one day (buying gifts, taking advantage of deals). Their velocity features spike. Their transaction amounts vary widely. Their merchant categories are unusual. The fraud model, trained on normal behavioral patterns, scores these as suspicious.

PayPal and other payment processors have documented this problem: during high-volume events, false positive rates spike sharply, declining legitimate transactions and frustrating real customers. The fraud model is doing its job correctly — it has detected a behavioral anomaly — but the anomaly is caused by a legitimate external event, not fraud. The model has no knowledge that it is Black Friday; it just sees that this user's behavior is wildly different from their historical baseline.

The engineering fix requires two things. First, the feature pipeline needs context signals: is today a known high-volume event? Is there a sale happening at this merchant? These signals can be precomputed as "event calendar features" that tell the model "today is unusual everywhere, so a behavioral spike is expected." Second, the model needs to be regularly evaluated against high-volume event holdout data, not just average-day data. If you evaluate your fraud model only on normal transaction volumes, you will not discover the false positive problem until Black Friday hits. Testing on simulated or historical high-event data is a standard part of fraud model validation at mature payment companies.

---

### Pattern 3: Search Ranking

```
SEARCH RANKING PIPELINE

  User Query: "Italian restaurant downtown"
       │
       ▼
  ┌────────────────────────────────────┐
  │  QUERY UNDERSTANDING               │
  │  - Parse intent (restaurant search)│
  │  - Extract entities (Italian, downtown)
  │  - Spell correction                │
  │  - Query expansion (synonyms)      │
  └─────────────────┬──────────────────┘
                    │
                    ▼
  ┌─────────────────────────────────────────────────────┐
  │  CANDIDATE RETRIEVAL (from millions of documents)   │
  │                                                     │
  │  Sparse retrieval: BM25 (keyword matching)          │
  │  Dense retrieval: Embedding similarity (ANN search) │
  │  Fusion: Reciprocal Rank Fusion (RRF) combines both │
  │                                                     │
  │  Output: ~1000 candidate documents                  │
  └─────────────────────┬───────────────────────────────┘
                        │ 1000 candidates
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  RANKING (features: query×document relevance,       │
  │           user context, freshness, CTR history)     │
  │  Model: LambdaMART / neural ranking                 │
  │  Output: ranked top 10                              │
  └─────────────────────────────────────────────────────┘
```

**The training data problem:** You train on click data (users clicked result 3 instead of result
1). But clicks are position-biased — result 1 gets clicked more just because it is at the top.
Naive training on raw clicks makes your model reinforce existing rankings, not learn true
relevance. Fix: position debiasing (propensity weighting) or unbiased learning-to-rank techniques.

#### Intern → Staff Progression (Search Ranking)

| Level | How they design the search ranking system |
|-------|------------------------------------------|
| **Intern** | Proposes BM25 keyword matching. Does not know how to rank results beyond keyword overlap. Does not think about position bias or how training labels are generated. |
| **L3** | Knows about learning-to-rank and that clicks are used as training labels. Does not know that click data is position-biased, so the model will reinforce existing rankings rather than learn true relevance. |
| **L4** | Recognizes position bias as a problem. Proposes adding dense retrieval (embedding similarity) alongside sparse retrieval (BM25) and knows about reciprocal rank fusion to combine them. Proposes NDCG as the offline evaluation metric. |
| **L5** | Designs the full retrieval-ranking pipeline with explicit latency budgets for each stage. Adds inverse propensity scoring to correct for position bias in click labels. Proposes A/B testing that measures search abandonment rate (users who search but do not click anything) as a proxy for ranking quality. |
| **L6** | Handles the training data problem at depth: how do you bootstrap the ranking model when you have no click data? (Start with BM25 rankings as weak supervision, then progressively improve with real click data corrected for position.) Designs freshness handling: new documents must be indexed and retrievable within minutes, not hours. Addresses the query reformulation loop: if a user searches, clicks nothing, and reformulates their query, that is a strong signal that the ranking failed — these sessions are gold for training. |

#### Real Incident (Search Ranking): Google's Early ML Transition and Position Bias Discovery

Google's original search engine (pre-2000) used PageRank and keyword matching, with no ML. The results were manually tunable: engineers could adjust weights on specific signals. When Google began introducing ML-based ranking in the early 2000s, they discovered a problem that had been invisible in the manual system: position bias was being baked into the training data.

The training data for ML ranking came from user clicks. But users click on the top result far more often than the bottom result, even when the bottom result is actually more relevant. When the ML model was trained naively on click data, it learned "result A at position 1 is good" — but it could not distinguish between "result A is intrinsically good" and "result A was at position 1 so it got clicked." The model reinforced existing rankings rather than discovering which results were truly better. Engineers noticed this when they ran a swap experiment: they swapped the positions of result 1 and result 2 for a sample of queries, and found that whichever result was shown at position 1 got more clicks, regardless of which one was originally ranked higher.

This discovery — that click data has structural bias baked in — led to the development of position debiasing techniques across the industry. Inverse propensity scoring (giving less weight to clicks at high positions, more weight to clicks at low positions) is now standard practice in learning-to-rank systems. The lesson for ML system design is that your training labels are not ground truth — they are measurements made under your current system's influence. Any time the current system shapes which examples get labeled, you need to explicitly model and correct for that influence in your training procedure.

---

### Pattern 4: Ad CTR Prediction

**Why it matters:** Ad systems are the highest-value ML systems ever built. A 0.1% improvement
in CTR prediction accuracy at Google or Meta translates to hundreds of millions of dollars per
year. The engineering constraints are extreme.

```
AD CTR PREDICTION FEATURES

  User features:         Ad features:           Context:
  - Demographics         - Ad category          - Time of day
  - Interest segments    - Historical CTR        - Device type
  - Recent searches      - Advertiser quality    - Geographic location
  - Purchase history     - Bid amount            - Current page content
  
  All combined → one feature vector → model → CTR prediction [0, 1]
  
  Scale: billions of ad auctions per day
  Latency: < 10ms (model is one part of a larger auction system)
  Updates: model must incorporate new click data within hours
```

**The scale problem:** Billions of ad impressions per day. The model must be updated near-real-
time because ads have very short lifecycles (a trending event ad has hours of relevance). Batch
retraining daily is too slow. Solution: **online learning with FTRL (Follow-The-Regularized-
Leader)**, which updates model weights after each mini-batch of clicks.

**Sparse categoricals:** Ad features are extremely high-dimensional and sparse (billions of
possible ad IDs, user IDs, keyword IDs). Standard neural networks cannot handle this scale.
Solution: embedding lookup tables (convert each ID to a dense low-dimensional vector), stored in
parameter servers. This is what Meta's DLRM and Google's Wide & Deep model architectures address.

#### Intern → Staff Progression (Ad CTR Prediction)

| Level | How they design the ad CTR prediction system |
|-------|---------------------------------------------|
| **Intern** | Proposes logistic regression on ad features. Does not think about the fact that ad IDs number in the billions or that the model must update faster than daily batch retraining allows. |
| **L3** | Knows that online learning is needed because ad click patterns change hourly. Does not know how to handle the sparse categorical feature problem (billions of possible ad IDs and user IDs that cannot be one-hot encoded). |
| **L4** | Proposes embedding lookup tables for sparse categoricals, stored in a parameter server. Knows about FTRL as the online learning algorithm. Understands the exploration problem for new ads with no click history. |
| **L5** | Designs the full system: FTRL online learning, embedding parameter server, real-time feature pipeline for user click signals updated within minutes, UCB for new ad exploration. Proposes cross-entropy loss as the training objective and AUC as the offline evaluation metric. Designs the shadow mode rollout for a new model version. |
| **L6** | Addresses the calibration problem: the model outputs a CTR probability that must be accurate in absolute terms (not just ranked correctly) because the ad auction uses the actual probability number in its pricing formula. A model with poor calibration that outputs 0.05 for a true CTR of 0.10 will underprice ads, losing revenue. Designs a calibration layer on top of the CTR model output. Also addresses the feedback loop from auction mechanics: if the model gives a high CTR score to certain ad types, those ads win auctions more often, get more impressions, and generate more training data — a rich-get-richer dynamic that must be corrected with exploration budgets for lower-scored ad segments. |

#### Real Incident (Ad CTR): Facebook's 2018 Reaction Algorithm Change

In 2018, Facebook made an internal decision to weight "angry" reaction emoji equally to "like" reactions in their engagement optimization model. The reasoning seemed reasonable at the time: any strong reaction means the content connected with the user. An angry reaction is still engagement — the user cared enough to respond.

The unintended consequence was immediate and significant. The ad optimization model — which used engagement signals to determine which posts and ads to show to which users — learned that content generating angry reactions performs just as well as content generating likes. Since outrage-inducing content is easier to generate than genuinely satisfying content, and since outrage spreads more virally (people share things they are angry about to express indignation), the model shifted content distribution toward increasingly divisive, anger-provoking material. Internal Facebook researchers documented this in a memo, later made public through the WSJ: the algorithm change was accelerating the spread of misinformation and hateful content, because those categories generated disproportionate angry reactions.

The technical lesson is about what your training signal is actually measuring. A "reaction" is a label. But not all labels are created equal — an angry reaction and a happy reaction are fundamentally different user states, and treating them identically in the loss function teaches the model that they are equivalent. In ad CTR prediction, this translates to a broader principle: the proxy metric you optimize (engagement, clicks, reactions) must be examined for whether it is actually aligned with your business goal (user satisfaction, long-term retention, advertiser value). When the proxy diverges from the goal — as angry reactions diverged from satisfaction — the model will find the divergence and exploit it, because that is exactly what optimization does. The fix is not a better model. The fix is a better training objective: separate reaction types, weight them differently, and include satisfaction signals (like return visit rate) as additional constraints.

---

### Common Mistakes — Part 8: Interview Patterns

```
COMMON MISTAKES SPECIFIC TO ML SYSTEM DESIGN INTERVIEWS

Mistake 1: Starting with the model
Wrong approach: "I would use a transformer-based model with 12 layers and
cross-attention between the query and document embeddings. For the loss function,
I would use a contrastive loss with in-batch negatives..."
Why it fails: You have spent 10 minutes on the least important part. The
interviewer is measuring systems thinking, not ML theory.
Right approach: "Before I talk about the model, let me establish the system
context: serving mode, latency budget, feature pipeline, and training data
source. The model is a component I'll slot in once the plumbing is designed."

Mistake 2: Not addressing scale in retrieval for recommendation systems
Wrong approach: "The ranking model scores each candidate and returns the top K."
Why it fails: If you have 100M items and don't say how you get from 100M to K
candidates, you have not designed a system. You have described a toy.
Right approach: Always name the two-stage architecture for any catalog > 1M items.
Stage 1 (approximate nearest neighbor retrieval) + Stage 2 (feature-rich ranking).
Name a specific retrieval technology: Faiss, ScaNN, Elasticsearch dense vectors.

Mistake 3: Using accuracy as the evaluation metric for imbalanced problems
Wrong approach: "Our fraud model achieves 99.8% accuracy."
Why it fails: A model that always predicts 'not fraud' achieves 99.99% accuracy
on a dataset where 0.01% of transactions are fraudulent. High accuracy on
imbalanced data is meaningless.
Right approach: "For fraud, accuracy is the wrong metric. I would evaluate on
AUC-ROC to measure discrimination ability, and precision/recall at my operating
threshold to measure the business trade-off. The key metric is: at our target
false positive rate (0.1%), what is our true positive rate (fraud detection rate)?"

Mistake 4: Treating the feedback loop as optional to mention
Wrong approach: Design the full system, say "and we'd monitor it," move on.
Why it fails: Interviewers at L6-level companies specifically probe for this.
Not mentioning it signals you have not operated a production ML system.
Right approach: Proactively bring it up: "I want to flag the feedback loop before
we go further. The model's decisions shape what data we collect, which shapes
the next model. This creates [specific risk for this system]. My mitigation is
[exploration policy / debiasing / secondary signal]. Do you want to go deep here?"

Mistake 5: Not giving numbers
Wrong approach: "We'd need a fast Redis lookup for features."
Why it fails: L6 answers have numbers. "Fast" is vague.
Right approach: "Redis lookup should be < 15ms at p99. If we're over that,
we need to look at connection pool sizing, key sharding, or moving the online
store closer to the model server geographically."
```

### The Full 45-Minute Interview Template

Here is the exact time allocation for a 45-minute ML system design interview.
This is the pacing an L6 candidate uses. Every minute is intentional.

```
TIME    ACTIVITY                                           DEPTH TARGET
──────────────────────────────────────────────────────────────────────────────
0:00    Clarify the problem                                3 good questions
        - What surface / use case specifically?
        - What scale (users, requests/sec, catalog size)?
        - What is the success metric (CTR? satisfaction? fraud loss rate?)

3:00    State the north star and constraints               1-2 minutes
        - Name the 3 constraints that will dominate design
        - Name which serving mode (online vs batch) and why

5:00    Draw the full system architecture (overview)       5 minutes
        - Start with the full diagram (all boxes)
        - Don't go deep yet — establish the skeleton
        - Name every box: data sources, feature pipeline,
          feature store (offline+online), training, model
          registry, serving, monitoring, feedback loop

10:00   Go deep on serving                                 8 minutes
        - Latency budget (with actual numbers)
        - Deployment pattern (shadow → canary → A/B)
        - Fallback hierarchy when model is unavailable
        - Specific: "Redis at p99 15ms, model at p99 50ms"

18:00   Go deep on feature pipeline / feature store        7 minutes
        - Which features need online store vs offline?
        - How do you prevent training-serving skew?
        - Name the freshness requirement per feature type
        - Address the most latency-sensitive feature (velocity)

25:00   Go deep on training pipeline                       5 minutes
        - Data source and label generation
        - Time-based split (not random split)
        - Retraining trigger and frequency
        - Evaluation gates before promotion

30:00   Address the feedback loop                          5 minutes
        - Name the specific feedback loop risk for this system
        - Name the mitigation (exploration budget, debiasing,
          label signal choice)
        - Give one concrete number or mechanism

35:00   Address monitoring / drift detection               5 minutes
        - Feature distribution monitoring (PSI, thresholds)
        - Prediction distribution monitoring
        - Business metric monitoring (with actual KPIs)
        - Alert → retrain → validate → promote pipeline

40:00   Address failure modes                              3 minutes
        - What if the feature pipeline is 3h late?
        - What if the model server is down?
        - What if a new model version causes a regression?
        Answer all three with specific fallback mechanisms.

43:00   Interviewer Q&A                                    2 minutes
        - They will go deeper on one area
        - This is where L6 vs L5 diverges: depth on the hard
          question, not just breadth

45:00   Wrap up
```

---

## Part 9: How to Talk About ML System Design in Interviews

### The L6 Signal

What the interviewer is measuring: do you understand the **engineering tradeoffs** in ML systems,
or do you only know ML theory? The trap most candidates fall into: spending 30 minutes discussing
model architectures (which type of neural network, which loss function) and zero minutes on the
plumbing. The interviewer cares about the plumbing.

### The Right Frame

Say this (or something like it) early in every ML system design interview:

> "I am going to treat the model as a black box that takes a feature vector and returns a
> prediction. My focus will be on: how we compute those features correctly (feature pipeline),
> how we serve predictions reliably at scale (serving infrastructure), how we detect when the
> model has gone stale (monitoring), and how we safely deploy new model versions (deployment
> strategy). I can go deeper on model choice if you want, but that is usually the least
> interesting engineering challenge."

This frame signals L6 thinking immediately. It tells the interviewer you know where the real
engineering problems live.

### Phrases That Signal Depth

Use these — not as buzzwords, but because you actually understand what they mean:

| Phrase | What it signals |
|--------|----------------|
| "training-serving skew" | You know the two phases exist and can diverge |
| "feature freshness SLA" | You think about freshness requirements per feature |
| "feedback loop delay" | You know labels take time to materialize |
| "two-stage retrieval-ranking" | You know how to handle scale in recommendation |
| "position debiasing" | You know click data is not clean signal |
| "point-in-time correct features" | You understand time leakage in training data |
| "online vs batch serving tradeoff" | You know when to precompute vs real-time compute |
| "model drift vs data drift" | You distinguish what changed: inputs or label relationship |

### What to Avoid

**Going too deep on model architecture:** "I would use a 12-layer transformer with cross-
attention between query and document embeddings..." — stop. Unless the interviewer specifically
asked about model architecture, this is a red flag. It signals you are an ML researcher, not an
ML systems engineer.

**Skipping the data pipeline:** Many candidates jump straight to "we train the model and serve
it." The interviewer notices. The hardest part of ML engineering is the data pipeline — how you
get clean, fresh, correctly-labeled features to your model. Spend real time on this.

**Ignoring failure modes:** What happens when the feature pipeline is late? What happens when
the model returns a null prediction? What happens when the online store is down? L6 engineers
think about failure modes. Add: "and for resilience, we need a fallback: if the ML model fails,
we fall back to [business rule / popularity ranking / cached prediction]."

### The Complete Answer Template for Any ML System Design Question

1. **Clarify the problem:** What is the prediction? What is the label? What is the latency
   requirement? What scale (users, requests/sec)?

2. **Identify serving mode:** Online (real-time) or batch (precomputed)? Justify why.

3. **Design the data pipeline:** Where does training data come from? How are labels generated?
   What is the feedback delay?

4. **Design the feature store:** Which features are needed? What freshness does each require?
   Online store or offline store?

5. **Design the training pipeline:** How often to retrain? How to validate data quality?
   How to evaluate model quality before deployment?

6. **Design the serving infrastructure:** Model server, latency budget, deployment pattern
   (shadow → canary → A/B → full rollout), fallback.

7. **Design monitoring:** Feature drift, prediction drift, business metrics, alerting,
   automatic retraining triggers.

8. **Address the feedback loop:** How does the system learn over time? What are the biases?
   How do you mitigate them?

---

## Real Life Product Incidents

### Incident 1: Uber Michelangelo (2017) — The Feature Store Origin Story

**What happened:** Before Uber built Michelangelo, every team at Uber had its own ML pipeline.
The surge pricing team had their own feature computation code. The ETA prediction team had their
own. The driver supply forecasting team had their own. Each team computed features slightly
differently — different timezone handling, different aggregation windows, different NULL handling.
When models were moved between teams or when systems were integrated, training-serving skew
was the default state. Models trained on one pipeline's features and served on another's.

**What went wrong technically:** There was no shared abstraction for "what is a feature and
how is it computed." Each team owned both their offline (training) and online (serving) feature
computation, and the two versions inevitably drifted. Additionally, there was massive duplicated
effort — six different teams had each built their own version of "user's trip count in last 30
days."

**What it teaches:** The feature store pattern exists because of this problem. By centralizing
feature computation in a single system where the same logic runs in both training (batch) and
serving (streaming) modes, you eliminate skew by construction. Michelangelo became the industry's
canonical example of a feature store and inspired Feast, Tecton, Hopsworks, and every other
feature store product.

---

### Incident 2: Amazon's Biased Hiring Algorithm (2018) — When Training Data Has History

**What happened:** Amazon built an ML model to screen resumes and rank job candidates. The model
was trained on 10 years of historical hiring decisions. Those decisions, made by humans over
a decade, reflected historical gender imbalances in the tech industry. The model learned the
pattern: resumes that looked like past successful hires (predominantly male) got high scores.

**What went wrong technically:** The model penalized resumes that included words like "women's"
(as in "women's chess club") and downgraded graduates of all-women's colleges. It had learned
these as negative signals not because they indicated poor performance, but because historically
few people with these attributes had been hired. The model was not predicting "will this person
be a good employee?" — it was predicting "does this person look like our historical hires?"

**What it teaches:** Training on historical data encodes historical biases. This is not a
monitoring or drift problem — it is a fundamental problem with what the model is learning.
Label quality here is: "was this person hired?" But hiring decisions are themselves biased.
The model learned to replicate human biases at scale. The lesson for ML system design: before
training on any outcome label, ask "are these outcomes the result of decisions we want to
perpetuate?" Audit model predictions for demographic parity, not just overall accuracy. Amazon
scrapped the model.

---

### Incident 3: Google Flu Trends (2009-2013) — Overfit to a Signal That Changed

**What happened:** Google built a model to predict flu outbreaks from search query data. The idea
was elegant: when people search for "flu symptoms" and "fever treatment," flu is probably spreading
in their region. The model was more timely than the CDC's official flu reports, which lagged by
two weeks. It worked well from 2009 to 2011.

**What went wrong technically:** In 2012-2013, Google Flu Trends consistently overestimated flu
prevalence by 2x. The model had overfit to search query patterns that changed for reasons
unrelated to actual flu. Media coverage of flu (including media coverage of Google Flu Trends
itself!) caused people to search for flu-related terms even when they were not sick. The model
had been trained in an era when "flu search volume = people getting sick." It was served in an
era when "flu search volume = flu is in the news." The relationship between the feature (flu
searches) and the label (actual flu cases) had fundamentally changed. This is concept drift.

**What it teaches:** Search queries are a social signal, not a medical signal. They reflect
media attention and public anxiety, not just underlying events. Any model that relies on social
signals must be designed with the expectation of concept drift — the meaning of signals changes
as culture, media, and public awareness change. Monitoring should have caught that flu trend
predictions were diverging from CDC ground truth. Drift detection with an external ground truth
signal would have triggered retraining or model deprecation much sooner.

---

### Incident 4: Twitter's Algorithmic Timeline (2016) — Optimizing the Wrong Metric

**What happened:** Twitter switched from a chronological timeline (tweets in order by time) to
an algorithmic timeline (tweets ranked by a model that predicted engagement). Engagement went
up. Users were seeing more tweets they interacted with. By the optimization metric, this was
a success.

**What went wrong technically:** The engagement model had learned that high-emotion content —
outrage, controversy, conflict — drives more interaction (replies, retweets, quote tweets). By
optimizing for engagement, the model amplified outrage content. Users saw more inflammatory
content, engaged with it (often in anger), and that signal trained the next model to show even
more inflammatory content. The feedback loop had tuned Twitter's algorithm toward content that
generated anger and division.

**What it teaches:** Engagement is not user satisfaction. Clicks are not happiness. Retweets are
not endorsements. When you optimize an ML model, it will find the shortest path to maximizing
your objective — even if that path is not what you intended. The system was technically working
correctly; the objective function was wrong. Multi-objective optimization (maximize engagement
subject to a "not outrage" constraint, or use satisfaction surveys as a secondary signal) is the
right design. This pattern — optimize for a measurable proxy, get unintended consequences — is
called **Goodhart's Law**: when a measure becomes a target, it ceases to be a good measure.

---

### Incident 5: Netflix Prize Winner Not Deployed (2009) — Serving Constraints are Real

**What happened:** Netflix ran a contest from 2006-2009, offering $1 million to whoever could
improve their recommendation accuracy by 10%. The winning solution: an ensemble of 107 different
models combined. It achieved the target improvement. The prize was paid. The model was never
used in production.

**What went wrong technically:** The winning ensemble model took too long to compute predictions.
Netflix's serving infrastructure at the time could not run 107 models in parallel and combine
their outputs within the latency budget. Additionally, Netflix's recommendation system had evolved
significantly since the contest data was collected (the contest data was from DVDs; Netflix had
shifted to streaming). The winning model solved the contest problem, not Netflix's actual problem.

**What it teaches:** You cannot design a model without considering serving constraints. If your
model takes 5 seconds to produce a recommendation and your latency requirement is 200ms, it does
not matter how accurate the model is — it cannot be deployed. This is why L6 engineers think
about the full serving pipeline from the start: latency budget, model size, inference cost,
hardware requirements. The best model you can actually deploy is better than the most accurate
model you cannot. This incident is cited constantly in ML engineering to justify building simpler,
faster models over more accurate but undeployable ones.

---

### Incident 6: Slack COVID Surge (2020) — When the World Changes Overnight

**What happened:** On March 13, 2020, the US declared a national emergency over COVID-19. Within
days, a significant fraction of the global office workforce was working from home and suddenly
using Slack all day instead of in-person offices. Slack's usage metrics shifted dramatically:
message volume increased sharply, usage hours extended far beyond the traditional 9-5 window,
new channels (remote-work-tips, #covid-anxiety, #watercooler) exploded in popularity, and the
device distribution shifted as people used personal laptops and phones.

**What went wrong technically:** Every ML model Slack had deployed was trained on pre-COVID
behavior patterns. Models for intelligent notifications (when to mute, when to interrupt), for
channel recommendations (suggesting relevant channels based on usage patterns), and for search
ranking (surfacing the most relevant messages) were all calibrated to a world where Slack was
used in defined office hours by people at their work desks. The simultaneous shift in all input
signal distributions caused widespread model degradation. Unlike a typical slow drift that
monitoring would catch over weeks, this was a near-instantaneous step-change in all signals
simultaneously.

**What it teaches:** Drift detection must be sensitive enough to catch rapid, simultaneous
changes across many features, not just gradual drift in individual features. Monitoring for
multi-variate distribution shift (all features shifting at once) requires different statistical
tools than univariate feature monitoring. Additionally, the incident taught the industry that
"black swan" events (pandemics, recessions, viral social media events) require a response
playbook: when did we last retrain? What is the fastest path to retraining on recent data?
Can we temporarily fall back to simpler rule-based systems while models are retrained?

---

## Exercises

**Exercise 1: Feature Freshness Analysis**

You are building a credit card fraud detection system. You have identified 20 features. Assign
each of the following to either "batch (daily)" or "streaming (real-time within 1 minute)" and
justify:
- User's annual income
- User's credit score
- Number of transactions in the last 60 minutes
- Merchant category code of the current transaction
- Whether the user's card was used in a different country in the last 24 hours
- User's average transaction amount over the last 90 days
- Current transaction amount

*For each feature, the key question is: if this feature is stale by 1 day, does the model make
a materially worse fraud decision?*

---

**Exercise 2: Training-Serving Skew Hunt**

You have a recommendation model. In training, average CTR on held-out data is 8%. In production,
measured CTR is 2%. List five specific things you would check to find the skew. For each,
describe how you would detect it and how you would fix it.

---

**Exercise 3: Latency Budget Allocation**

Your search ranking API must respond in 200ms total. You have: a Redis feature lookup, a BM25
retrieval step over 10 million documents, an embedding-based retrieval step (ANN search), and
a LambdaMART ranking model over 200 candidates. Allocate the latency budget to each component.
What do you do if the ANN search alone takes 150ms?

---

**Exercise 4: Feedback Loop Identification**

For each of the following systems, describe the feedback loop that could form and what its
long-term effect would be:
- A news article ranking system that optimizes for time-on-page
- A job listing recommendation system that optimizes for application rate
- A content moderation model that flags content for human review, and human decisions are used
  as training labels

---

**Exercise 5: Monitoring System Design**

Design the monitoring system for an e-commerce product recommendation model. Specifically:
- What metrics would you monitor at the feature level?
- What metrics would you monitor at the prediction level?
- What business metrics would you track?
- What are your alert thresholds and actions at each threshold?
- How long is your monitoring window (hourly? daily?), and why?

---

**Exercise 6: Cold Start System Design**

You are launching a new content streaming platform from scratch. On Day 1, you have 10,000
registered users, 50,000 content items, and zero interaction data. Design the recommendation
system for Day 1, Day 30 (after 1 month of data), and Day 365 (after 1 year). How does the
architecture evolve?

---

**Exercise 7: The Two-Stage Trade-off**

You are designing a recommendation system for a music streaming platform. You have 80 million
tracks and need to recommend 20 tracks per user. Your ML team proposes two architectures:
- **Option A:** One stage. Train a single model that scores all 80 million tracks. Serve the
  top 20.
- **Option B:** Two stages. Stage 1 retrieves the top 500 tracks using embeddings. Stage 2
  re-ranks those 500 using a feature-rich model.

Analyze the latency, accuracy, and engineering complexity of both options. Which do you choose
and why?

---

## Homework

**Assignment 1: Read "Machine Learning: The High-Interest Credit Card of Technical Debt"**

This 2014 paper by Sculley et al. (Google) is the foundational paper on ML system debt. It
coined the term "CACE" (Changing Anything Changes Everything) for ML systems. After reading,
write a one-page summary identifying: (a) the three types of ML system debt you think are most
common in practice, and (b) for each, what engineering practice prevents it.

The paper is freely available at: https://papers.nips.cc/paper/2015/file/86df7dcfd896fcaf2674f757a2463eba-Paper.pdf

---

**Assignment 2: Design a Ride-Share Surge Pricing ML System**

Design the ML system that predicts surge pricing for a ride-sharing app (like Uber/Lyft).
Cover: what features does the model need (supply, demand, time, location, weather, events)?
What is the training pipeline? How often does it retrain? What are the serving latency
requirements? What are the feedback loops (does surge pricing change supply and demand in
ways that affect future predictions)?

Write this as a 2-3 page design document, as if presenting to your team.

---

**Assignment 3: Audit an Existing ML System for Drift Risk**

Pick any production ML system you have worked on or have access to. Audit it for drift risk:
- What are the top 5 features? When were they last validated against current data distributions?
- Is there a concept drift risk? What real-world events could change the label relationship?
- What monitoring exists? What is missing?
- What is the current retraining schedule? Is it appropriate?

If you do not have access to a production system, use Netflix's recommendation system (described
publicly in engineering blog posts) as your case study.

---

**Assignment 4: Build a Toy Feature Store**

Implement a minimal feature store in Python with two modes:
- **Offline mode:** Given a list of user IDs and a historical date, return the feature values
  as of that date (use a CSV file as your "data warehouse").
- **Online mode:** Given a single user ID, return the current feature values in < 50ms
  (use an in-memory dictionary as your "Redis").

Demonstrate that both modes produce the same feature value for the same user at the same point
in time. This is the core guarantee a real feature store must provide.

---

**Assignment 5: Interview Practice — Answer Three ML System Design Questions**

Practice answering these three questions out loud, aiming for 45 minutes each:

1. "Design YouTube's video recommendation system."
2. "Design a real-time fraud detection system for a payment processor processing 10,000
   transactions per second."
3. "Design the ML system that determines which ads to show on a search results page."

For each answer, structure it using the 8-step template from Part 9. Record yourself and
review: did you spend time on the data pipeline? Did you address the feedback loop? Did you
mention monitoring? Did you propose a deployment strategy?

---

### Specific Phrases to Use vs Avoid

The following is a comparison of L4-level vs L6-level phrasing for common concepts.
Use the L6 column:

```
TOPIC                L4 PHRASING                    L6 PHRASING
──────────────────────────────────────────────────────────────────────────────
Feature freshness    "We'll use Redis for fresh      "Velocity features (txn count
                     features"                       in last 1hr) must be < 60
                                                     seconds stale — needs streaming
                                                     (Kafka + Flink stateful window).
                                                     Demographic features can be
                                                     24h stale — batch job, offline
                                                     store only. I size the online
                                                     store for streaming features only."

Training-serving     "We'll use a feature store      "The risk is that training code
skew                 to prevent skew"                and serving code compute the same
                                                     feature differently. I'd use Feast
                                                     feature definitions: one Python
                                                     function, deployed in batch mode
                                                     for training and streaming mode
                                                     for serving. Skew is prevented
                                                     by construction, not by process."

Model deployment     "We'll do a canary release"     "Shadow mode first: new model gets
                                                     same traffic as old model, predictions
                                                     are logged but NOT served. We compare
                                                     prediction distributions for 48 hours.
                                                     Then 1% canary: new model serves 1%
                                                     of users. Automated rollback if p99
                                                     latency increases >20% or business
                                                     KPI drops >3%. Ramp: 1% → 5% → 25%
                                                     → 100% with 24h hold at each stage."

Feedback loop        "We'll add exploration to       "5% of slots are exploration: randomly
                     prevent filter bubbles"         sampled from below the model's top-200.
                                                     These are logged with exploration=true
                                                     and excluded from the main training
                                                     signal. I run a weekly analysis of
                                                     exploration slot CTR to identify
                                                     undervalued items. The exploration
                                                     budget is a separate model serving
                                                     decision, not baked into ranking."

Monitoring           "We'll monitor for drift"       "I'd compute PSI per feature hourly
                                                     for high-volatility features, daily
                                                     for stable ones. Alert at PSI > 0.10,
                                                     trigger retraining at PSI > 0.25.
                                                     Separately monitor the joint feature
                                                     distribution (Mahalanobis distance)
                                                     to catch correlated multi-feature
                                                     shifts that univariate PSI misses."
```

### The One Question That Separates L5 from L6

In virtually every ML system design interview, there is a question the interviewer uses to
separate L5 from L6 candidates. It usually sounds like:

- "What happens to your system if the feature pipeline is 6 hours late today?"
- "How do you know if your feedback loop is causing harm?"
- "If the new model you just deployed is producing bad predictions, how do you find out
  and what do you do in the next 10 minutes?"

The L5 candidate answers the surface question: "We'd roll back to the previous model."

The L6 candidate answers the deeper question: "First, we need to detect it. I'd have an
alert on prediction distribution shift — if the mean fraud score today is 0.08 and it
suddenly moves to 0.22, that fires within 5 minutes. We investigate: is this a real fraud
spike, or did the feature pipeline break and send null values to the model? Check the feature
freshness dashboard — if purchase_count_7d is null for 20% of requests, that is a pipeline
bug. Roll back to the last known good model (registry stores the previous version). Alert
the data pipeline team. Simultaneously activate the rule-based fallback so we do not approve
obvious fraud while the model is broken. Post-incident: add an automated check that fires
if the null rate of any feature exceeds 5%, before the impact reaches the model."

The depth is not in knowing more — it is in thinking through the **failure sequence end-to-end**,
from detection to mitigation to prevention. That is L6.

---

## Quick Reference: Numbers Every L6 Candidate Should Know

In ML system design interviews, the candidates who quote specific numbers always sound more
credible than those who say "fast" and "slow." Memorize these rough benchmarks:

```
COMPONENT                           TYPICAL LATENCY        NOTES
──────────────────────────────────────────────────────────────────────────────
Redis lookup (HGETALL)              1-5ms                  p50; p99 ~15ms
PostgreSQL query (simple, indexed)  5-15ms                 p50; p99 ~50ms
BigQuery query (100GB table scan)   5-30 seconds           batch, not serving
Kafka event → Flink window update   100ms-2 seconds        depends on window size
XGBoost inference (100 trees)       2-10ms                 tabular features, CPU
Neural net inference (small, CPU)   10-50ms                depends on model size
Neural net inference (GPU)          2-20ms                 with GPU acceleration
LLM inference (7B param model)      500ms-5 seconds        depends on context length
ANN search (Faiss, 100M vectors)    5-30ms                 with GPU; 50-200ms CPU
Feature store write (batch)         minutes-hours          BigQuery / Parquet
Feature store write (streaming)     seconds-minutes        Flink → Redis

SCALE BENCHMARKS
──────────────────────────────────────────────────────────────────────────────
YouTube                 2B monthly users, 800M videos, 500 hours uploaded/min
Netflix                 220M subscribers, 36,000 hours of content, 700k streams
Google Ads              8.5B ad auctions per day (~100,000/sec)
Meta ads                ~10M advertisers, billions of ad impressions per day
Stripe payments         ~1,000 transactions/sec average, ~10,000/sec peak
Uber rides              ~10M trips per day (~120/sec)
Amazon search           ~300M products, billions of search queries per month

DRIFT DETECTION THRESHOLDS (industry standard)
──────────────────────────────────────────────────────────────────────────────
PSI < 0.05              No significant drift, continue monitoring
PSI 0.05-0.10           Minor drift, investigate
PSI 0.10-0.25           Moderate drift, consider retraining
PSI > 0.25              Severe drift, trigger retraining + alert

FEATURE STORE SIZING (rough guidance)
──────────────────────────────────────────────────────────────────────────────
1M users, 50 features   ~400MB Redis (8 bytes per feature value × 50 × 1M)
100M users, 50 features ~40GB Redis (need sharding / Redis Cluster)
1B users, 50 features   ~400GB Redis (expensive; consider tiered storage)

Note: At 1B users, many features move to a different online store technology:
Bigtable (Google) or DynamoDB (AWS) at lower per-read cost, slightly higher latency.
```

---

## Chapter Summary

ML system design at L6 is not about knowing more ML than other candidates. It is about
understanding the systems engineering challenges that make ML hard in production:

1. **The two-phase problem** (training vs serving) creates a permanent tension that the feature
   store resolves through shared computation. A feature store's key guarantee: the same
   feature value at the same timestamp, whether you are in training or serving mode.

2. **Training-serving skew** is the most common production bug. It is prevented by writing
   one canonical feature definition (in Feast, Tecton, or a shared library) that executes
   in both batch and streaming modes. Two implementations = guaranteed skew.

3. **The feedback loop** means your model's predictions affect its own training data. Without
   intervention, the feedback loop causes filter bubbles, rich-get-richer dynamics, and
   blind spots for new patterns. Manage it through exploration budget (5% random slots),
   position debiasing, and label delay handling.

4. **Drift detection** is how you find out your model is wrong before users tell you. Monitor
   features (PSI, hourly), prediction distribution, and business metrics in parallel.
   PSI > 0.10 = investigate. PSI > 0.25 = retrain. Add multivariate drift detection (Mahalanobis
   distance) for black swan events where all features shift at once.

5. **Serving constraints are real.** The Netflix Prize winner was never deployed. Design for
   the latency budget you actually have. Know the numbers: Redis p99 = 15ms, XGBoost = 10ms,
   neural net on CPU = 50ms. Sum them up. Build in a fallback hierarchy for when the
   model server is unavailable.

6. **Four interview patterns** repeat constantly:
   - Recommendation: two-stage retrieval (ANN, 20ms) → ranking (feature-rich, 100ms)
   - Fraud: rule engine (5ms) → real-time velocity features (Redis, 30ms) → XGBoost (10ms)
   - Search: BM25 + dense retrieval fusion → LambdaMART ranking with position debiasing
   - Ads: FTRL online learning, embedding parameter server, calibration layer on top of CTR

7. **The interview signal** is proactively raising failure modes — the feedback loop,
   training-serving skew, the label delay problem — before the interviewer asks. L5 waits
   to be asked. L6 names the risks first.

The frame that gets you hired at L6: "I design the plumbing that feeds the model, serves its
predictions, and keeps it honest over time." Say it. Mean it. Demonstrate it by spending the
majority of your interview time on the plumbing, not the model.
