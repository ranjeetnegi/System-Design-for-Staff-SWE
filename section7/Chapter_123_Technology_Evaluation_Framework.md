# Chapter 123 — Technology Evaluation Framework

> *"The best technology is the one your team can operate at 3am. The second best is the one that solves your actual problem. Pick based on evidence, not enthusiasm."*

---

```
┌──────────────────────────────────────────────────────────────────────────────┐
│              AT-A-GLANCE: TECHNOLOGY EVALUATION FRAMEWORK                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  THE TRAP       Engineers pick the most interesting technology,              │
│                 not the most appropriate one. Evaluation prevents this.      │
│                                                                              │
│  BUY vs BUILD   Build only when: off-shelf can't meet your requirements     │
│                 AND you can afford to maintain it forever.                  │
│                 Default: use existing tools. Building is 10× more expensive │
│                 than it looks upfront.                                       │
│                                                                              │
│  CRITERIA FIRST Define what "winning" looks like BEFORE evaluating options. │
│                 Options look completely different depending on criteria.     │
│                                                                              │
│  PoC SCOPE      A PoC answers: "Can this technology solve our specific       │
│                 problem?" NOT "What can this technology do?"                 │
│                 Time-box: 1-2 weeks. One specific question.                 │
│                                                                              │
│  REVERSIBILITY  How hard is it to undo this decision in 2 years?            │
│                 High lock-in = needs higher bar of evidence to adopt.       │
│                                                                              │
│  L5 SIGNAL      Runs a structured evaluation with criteria + PoC + doc.     │
│                 Can recommend and defend a choice with evidence.            │
│  L6 SIGNAL      Designs the org's evaluation process. Knows which           │
│                 decisions need formal eval vs. quick judgment call.         │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Why Technology Decisions Are Hard

*(Intern → L3 level)*

Imagine your team needs a message queue. You research options: Kafka, RabbitMQ, SQS, Pulsar, NATS, Redis Streams, Kinesis. Each has a conference talk, a blog post from Netflix, and a GitHub star count over 10,000. How do you decide?

Most engineers do one of two things:

```
COMMON MISTAKE 1: Pick what you know
  "We've used RabbitMQ before — let's use it."
  The problem: what you know may not fit what you need.
  RabbitMQ is great for task queues; poor fit for event streaming at 1M/sec.

COMMON MISTAKE 2: Pick what's trending
  "Everyone is using Kafka. Let's use Kafka."
  The problem: Kafka solves Kafka-scale problems.
  For a team of 5 engineers with 10K messages/day, Kafka is massive overkill.
  Operational burden is enormous. The trendy choice becomes a liability.
```

**Why these mistakes are costly:**

Technology decisions have long tails. A database chosen in 2020 is still running in 2026. A message queue adopted without evaluation becomes a dependency for 30 services. The cost of a bad decision compounds over years.

```
Cost of a good decision:         Cost of a bad decision:
  1-2 weeks evaluation              2-4 weeks evaluation (skipped)
  + 1 week PoC                      + 6 months integration
  + 2 weeks migration               + 3 years fighting its limitations
  + 1 eval doc                      + 12 months to migrate away
  ───────────────────               ──────────────────────────────
  ~4 weeks total                    ~4 years total
```

**The real question to ask:**

Not "what's the best technology?" — there is no universal best. The question is:

**"What is the best technology for our specific problem, given our team's skills, our scale, our reliability requirements, and the cost of being wrong?"**

Every word in that sentence matters.

```
ASCII: the evaluation mindset

Wrong approach:               Right approach:

  "What can X do?"             "What do we need to do?"
       │                              │
       ▼                              ▼
  Demo everything            Define requirements first
       │                              │
       ▼                              ▼
  Wow, Kafka can do           Can X meet requirement 1?
  100M messages/sec!          Can X meet requirement 2?
       │                              │
       ▼                              ▼
  Let's use Kafka!            Score candidates.
                              Pick the best fit.
```

**Real example: Segment's 2017 Kafka migration (and reversal)**

In 2017, Segment migrated their data pipeline to Kafka to handle scale. Two years later, they wrote a post explaining why they were moving away from Kafka. The problem: Kafka required significant operational expertise they didn't have. They spent more engineering time managing Kafka than building product. They moved to a simpler solution. Lesson: the right technology is the one your team can operate, not the one that handles the most scale.

**Brainstorming Questions:**
1. Your teammate says "let's use [trendy technology X] — it worked at Facebook." What follow-up questions would you ask before agreeing?
2. A bad technology decision was made 2 years before you joined the team. You're now asked to evaluate a replacement. What information do you gather to understand why the original decision was made?
3. Why is "everyone else is using it" a weak justification for adopting a technology? When IS it a reasonable signal?
4. Think of a technology decision your current team made. In hindsight, was it evaluated systematically or picked intuitively? What would have changed with a more structured approach?

---

## Part 2: The Decision Spectrum — Buy, OSS, or Build

*(Intern → L3 level)*

Before evaluating specific technologies, understand which category of solution you're looking for. There are three options, and they have very different costs and trade-offs.

```
┌─────────────────────────────────────────────────────────────────────┐
│           THE BUILD / OSS / BUY SPECTRUM                           │
├─────────────┬───────────────────────────────────────────────────────┤
│  BUY        │ Pay a vendor for a managed service.                  │
│ (SaaS/PaaS) │ Examples: Datadog (monitoring), Stripe (payments),   │
│             │ Twilio (SMS), Snowflake (data warehouse)             │
│             │                                                       │
│             │ Pros: fast to deploy, vendor handles ops,            │
│             │       no infra to manage                             │
│             │ Cons: expensive at scale, vendor lock-in,            │
│             │       data leaves your infrastructure                │
│             │ Use when: the domain is not your core competency     │
├─────────────┼───────────────────────────────────────────────────────┤
│  OSS        │ Use open-source software you run yourself.           │
│             │ Examples: PostgreSQL, Kafka, Redis, Kubernetes,      │
│             │ Prometheus, Elasticsearch                            │
│             │                                                       │
│             │ Pros: free licensing, full control, large community  │
│             │ Cons: you own operations, upgrades, scaling          │
│             │ Use when: you have ops expertise AND need control    │
├─────────────┼───────────────────────────────────────────────────────┤
│  BUILD      │ Write it yourself from scratch.                      │
│ (custom)    │ Examples: custom rate limiter, internal job queue,   │
│             │ bespoke recommendation engine                        │
│             │                                                       │
│             │ Pros: perfectly fits your requirements               │
│             │ Cons: you build AND operate AND evolve it forever    │
│             │ Use when: NOTHING else fits your requirements        │
└─────────────┴───────────────────────────────────────────────────────┘
```

**The "build" trap:**

"How hard can it be? We'll just build a simple queue." This underestimates what "build" really means:

```
What you think you're building:         What you're actually building:
  A simple message queue                  A message queue
                                          + persistence (what if the process crashes?)
                                          + backpressure (what if consumers are slow?)
                                          + acknowledgment (what if processing fails?)
                                          + monitoring (is it healthy?)
                                          + dead-letter queue (what happens to failed messages?)
                                          + exactly-once semantics (duplicate detection)
                                          + scaling (what if volume 10×s?)
                                          + security (who can publish/consume?)
                                          + operations (on-call, incidents, upgrades)

This is why Kafka exists. A team of 50 built it over years.
You will not build something equivalent in a sprint.
```

**The total cost of ownership (TCO) framework:**

```
TCO = initial build cost + ongoing maintenance cost over N years

For buying:    TCO = subscription fee × N years
For OSS:       TCO = 0 + (engineer-hours/year × N years × $cost/hour)
For building:  TCO = initial dev cost + (engineer-hours/year × N years × $cost/hour)

Rule of thumb:
  "Build" option: multiply your initial estimate by 3-5×.
                  You will underestimate scope, complexity, and maintenance.
                  
  "Buy" option: add the fully-loaded cost (annual subscription + integration
                engineering + vendor management + migration cost if switching).
```

**The reversibility question:**

Before choosing the buy vs. OSS vs. build dimension, ask: "If this turns out to be wrong in 2 years, how hard is it to switch?"

```
Easy to reverse:      Hard to reverse:
  Logging (swap     →   Primary database (all data in vendor schema)
   log exporter)      
  Monitoring tool   →   Auth system (user data, OAuth tokens in vendor)
  Email provider    →   Message queue (downstream services coupled to API)
  A/B test platform →   Data warehouse (years of historical data)
```

Higher lock-in requires higher confidence before adopting.

**Brainstorming Questions:**
1. Your team is evaluating whether to use Twilio (SaaS) or build an SMS service in-house. What information would you need to make a recommendation? What would push you toward Twilio? What would push you toward building?
2. Your company uses a SaaS monitoring tool at $30K/year. At what scale would self-hosting Prometheus + Grafana (open source) become cheaper? What other factors would you consider beyond price?
3. A team says "we built our own authentication service because we needed custom logic." What questions would you ask to evaluate whether building was the right decision?
4. You're evaluating two message queues: Kafka (OSS, self-hosted) and AWS SQS (managed SaaS). Your team has 3 engineers and 10K messages/day. Which would you lean toward, and why?

---

## Part 3: Defining Evaluation Criteria Before Looking at Options

*(L3 → L4 level)*

The most important step in technology evaluation is the one most teams skip: defining what "good" looks like BEFORE they start evaluating options.

Without criteria, every evaluation becomes subjective. Two engineers evaluate the same two databases: one prefers Postgres (familiar), the other prefers MongoDB (exciting). They argue for days. Neither can convince the other because there's no shared definition of success.

**Why criteria-first matters:**

```
Wrong order:                        Right order:
  1. Look at options                  1. Write down your requirements
  2. Get excited about features       2. Define measurable criteria
  3. Pick the one that felt best      3. Now evaluate options against criteria
  4. Justify the choice afterward     4. The best fit becomes obvious
  
Problem with wrong order:           Benefit of right order:
  "We picked X because it's fast."    "We need < 10ms p99 write latency,
  Fast compared to what?              support for 50K QPS, horizontal
  Fast for what operation?            scaling, and ACID transactions.
  The justification comes AFTER        X scored 4/4, Y scored 2/4."
  the decision — not before.
```

**The five categories of evaluation criteria:**

```
┌──────────────────────────────────────────────────────────────────────┐
│           EVALUATION CRITERIA CATEGORIES                            │
├────────────────────┬─────────────────────────────────────────────────┤
│  1. FUNCTIONAL     │ Does it do what we need it to do?               │
│                    │ Example: "Supports exactly-once delivery"        │
│                    │ "Can run geospatial queries"                     │
│                    │ "Supports multi-tenancy"                         │
├────────────────────┼─────────────────────────────────────────────────┤
│  2. PERFORMANCE    │ Does it meet our scale and latency requirements? │
│                    │ Example: "p99 write latency < 10ms at 50K QPS"  │
│                    │ "Can store 10TB of data"                         │
│                    │ "Throughput > 100K messages/sec"                 │
├────────────────────┼─────────────────────────────────────────────────┤
│  3. OPERATIONAL    │ Can we run this reliably?                        │
│                    │ Example: "Managed service (we don't operate it)" │
│                    │ "Has Kubernetes operator"                        │
│                    │ "Team has 2+ engineers with experience"          │
├────────────────────┼─────────────────────────────────────────────────┤
│  4. ECOSYSTEM      │ Does it fit our stack?                           │
│                    │ Example: "Has Go SDK"                            │
│                    │ "Integrates with our observability stack"        │
│                    │ "Active community, > 3 major releases/year"     │
├────────────────────┼─────────────────────────────────────────────────┤
│  5. RISK           │ What can go wrong?                               │
│                    │ Example: "Vendor is > 5 years old, Series C+"   │
│                    │ "License: Apache 2.0 (no surprise re-licensing)" │
│                    │ "Migration path exists if we need to switch"     │
└────────────────────┴─────────────────────────────────────────────────┘
```

**Turning requirements into criteria — worked example:**

Your team needs a search system. The requirement: "users need to search our product catalog."

```
Vague requirement:             Specific, measurable criteria:
"Needs to be fast"         →   "p99 search latency < 200ms at 1,000 QPS"
"Needs to be scalable"     →   "Support 100M indexed documents without
                                re-architecture"
"Needs to be maintained"   →   "Receives security patches within 30 days
                                of CVE disclosure"
"We need relevance"        →   "Supports BM25 ranking AND custom
                                relevance boosting by field"
"Easy to use"              →   "Has a Python SDK AND a REST API"
"Cost-effective"           →   "Total cost of ownership < $5K/month
                                at target scale"
```

Now you can score Elasticsearch, OpenSearch, Typesense, Meilisearch, and Pinecone against these 6 criteria. The conversation changes from "I prefer X" to "X scores 5/6 criteria, Y scores 4/6."

**Criteria weighting:**

Not all criteria are equal. Define: which criteria are **must-have** (deal-breakers if not met) vs. **nice-to-have** (scored but not blocking).

```
Must-haves (disqualifying):
  ✦ p99 < 200ms at 1,000 QPS
  ✦ Supports 100M documents
  ✦ Has Go and Python SDKs

Nice-to-haves (scored 1-5):
  ○ Multi-language search (Spanish, Hindi)
  ○ Typo correction
  ○ Managed service option
  ○ Active community (> 500 GitHub stars/month)
```

Any candidate that fails a must-have is eliminated. Then score the rest on nice-to-haves.

**Brainstorming Questions:**
1. Your team needs to choose a time-series database for metrics storage. Write 5 measurable evaluation criteria (be specific — include numbers where relevant).
2. Two engineers on your team have conflicting opinions about a technology. One prefers Postgres, one prefers MongoDB. How would you use the criteria framework to resolve the disagreement objectively?
3. You're evaluating 4 options. After defining criteria, you realize none of them meet all must-haves. What are your options? (Think: relax a must-have, build custom, reconsider the problem framing)
4. Who should be involved in defining the evaluation criteria? What happens if criteria are defined by only one person? What about if criteria are defined by committee?

---

## Part 4: The PoC — What It Should Answer, and What It Shouldn't

*(L4 level)*

A Proof of Concept (PoC) is a time-boxed experiment to answer one specific question. It is not a feature build. It is not an integration. It is an answer to a narrow question.

**The PoC question:**

Before writing a line of PoC code, write down: "After this PoC, we will know whether ____."

```
Good PoC question:
  "After this PoC, we will know whether Elasticsearch can serve 1,000 QPS
   at < 200ms p99 latency with our product catalog schema and query patterns."

Bad PoC questions:
  "We will know if Elasticsearch is good."   (too vague — good for what?)
  "We will build the search feature."        (that's not a PoC — it's a build)
  "We will compare Elasticsearch vs. Typesense vs. Meilisearch."
                                             (too broad — pick one question)
```

**The PoC scope rules:**

```
1. TIME-BOX IT
   1-2 weeks maximum.
   If it takes longer, the question is too broad. Narrow it.
   Rule: if you can't answer the question in 2 weeks, split it into
         two sequential PoCs.

2. ONE QUESTION ONLY
   "Can X handle our load?" OR "Does X support feature Y?" — not both.
   Multiple questions = no clear conclusion.

3. USE PRODUCTION-LIKE DATA
   Fake data shows that the technology works in happy-path scenarios.
   Your actual data will have: edge cases, encoding issues, long strings,
   null values, schema inconsistencies.
   If you can't use production data, generate realistic synthetic data.

4. TEST YOUR WORST CASE
   Don't PoC with your average case.
   Your average product query has 3 words. Your worst case has 50 words
   with special characters in 3 languages.
   The PoC must handle the worst case, not the easy case.

5. DOCUMENT THE CONCLUSION
   The PoC result must be: "Yes, X can do Y" or "No, X cannot do Y."
   "It was interesting" is not a PoC conclusion.
```

**What a PoC is NOT for:**

```
❌ Proof that a technology is generally good
   → That's a review article, not a PoC.

❌ A shortcut to justify a decision you've already made
   → "We already decided on Kafka, let's do a PoC to confirm."
   → This is confirmation bias disguised as rigor.

❌ A chance to build the real thing without approval
   → "We'll do a quick PoC" that turns into a 3-month integration.
   → If the PoC produces production code, it wasn't a PoC.

❌ A demo
   → A demo shows best-case behavior. A PoC tests worst-case.
```

**PoC example — evaluating Typesense for product search:**

```
PoC question:
  "Can Typesense return p99 < 200ms for our catalog search queries
   with a 10M-product dataset, including typo correction and faceting?"

PoC setup (3 days):
  1. Export 10M real products from production (anonymized if needed)
  2. Define the schema (same fields as production: name, description,
     category, price, tags)
  3. Index the 10M products
  4. Write the 10 most common query patterns from production logs
  5. Build a k6 load test that runs these 10 queries at 1,000 QPS

PoC execution (2 days):
  1. Run load test. Record p50, p99, error rate
  2. Test typo correction: "samsugn galaxy" → "samsung galaxy"
  3. Test faceting: filter by category + price range simultaneously
  4. Test empty results: obscure queries that return 0 results
  5. Test index update: update 10K products, measure search result freshness

PoC conclusion (1 day):
  "Typesense passed: p99 = 87ms at 1,000 QPS. Typo correction works.
   Faceting latency < 100ms with 6 facets.
   One failure: index update delay is 30-60 seconds (near-real-time,
   not real-time). Acceptable for product catalog — products change
   slowly. NOT acceptable for inventory levels — we'll query inventory
   separately."
```

The PoC took 6 days and produced a clear, specific answer. The team can now make a decision with evidence.

**Brainstorming Questions:**
1. You're tasked with a PoC for a new caching layer. Write the PoC question, specify the time box, and list exactly what you will and won't build during the PoC.
2. Your team's PoC is on day 10 of a 5-day time box. The engineer running it keeps finding new things to test. How do you handle this? What's the risk of extending the PoC indefinitely?
3. A PoC was done using synthetic data and showed great results. The team adopted the technology. 3 months later in production, performance is poor with real data. What went wrong in the PoC design?
4. Two PoCs were run: one for Elasticsearch, one for Typesense. Both met the functional requirements. The Elasticsearch PoC ran for 3 weeks; the Typesense PoC ran for 1 week. Does the longer PoC time indicate a better evaluation? What might it indicate instead?

---

## Part 5: Build vs. Buy — The Full Cost Math

*(L4 level)*

The build vs. buy decision is one of the most consequential in engineering. "Building" feels empowering and feels like it saves money. In practice, the full cost almost always surprises teams.

**The buy cost:**

```
Upfront:
  Integration engineering: 2-4 weeks to connect the vendor API
  Evaluation and contract negotiation: 1-2 weeks
  
Ongoing (per year):
  Subscription fee
  Vendor management (1-2 hours/week of eng time)
  Staying current with API changes
  Migration risk (if vendor raises prices or changes terms)
```

**The build cost — the honest accounting:**

```
Upfront:
  Design and architecture: 2-4 weeks
  Initial development: 4-12 weeks
  Testing (unit, integration, load): 2-4 weeks
  Documentation: 1 week
  Security review: 1-2 weeks
  
Ongoing (per year, every year):
  Bug fixes: 4-8 weeks
  Feature additions: 8-16 weeks (you'll always be asked to add features)
  Security patches: 2-4 weeks
  Scaling work: 4-8 weeks as traffic grows
  On-call coverage: 4-8 hours/week × 52 weeks = 200-400 hours/year
  New-hire onboarding: explaining your custom system to every new engineer
  
The "every year" cost is the one engineers always forget.
After 3 years: upfront cost is a small fraction of total cost.
```

**The build vs. buy decision tree:**

```
1. Does a commercial solution solve > 80% of your requirements?
   No → seriously consider building. Commercial solutions may not exist.
   Yes → continue to step 2.

2. What is the 3-year TCO for buying vs. building?
   (Be honest about the build cost. Include ops, on-call, maintenance.)
   If buy is cheaper → strong lean toward buy.
   If build is cheaper → continue to step 3.

3. Is this part of your core competency?
   "We are a payments company. Building a payments system = core."
   "We are a payments company. Building a video transcoder = not core."
   Non-core → lean toward buy even if slightly more expensive.
   Core → building gives you control and competitive advantage.

4. What is the reversibility cost?
   If you buy and want to switch in 3 years: migration cost?
   If you build and want to stop: decommission cost + replacement cost?
   Higher reversibility = lower risk tolerance = lean toward buy.

5. Do you have the expertise to build AND operate this?
   "We have 1 engineer who knows Elasticsearch internals."
   1 engineer = single point of failure. What happens when they leave?
   If no: the "build" option has higher hidden risk than it appears.
```

**A worked example: rate limiter**

```
Team: 8 engineers. Scale: 10K API requests/sec. Existing stack: Redis, Go.

Option 1: Build a rate limiter
  Initial build: 2 weeks
  Uses: Redis + sliding window algorithm + Go middleware
  Maintenance: 2-4 hours/week (monitoring, bug fixes, edge cases)
  Cost per year: ~$50K (0.1 engineer)

Option 2: Buy (AWS WAF rate limiting)
  Integration: 3 days
  Cost: $5K/year for 10K req/sec
  Maintenance: near zero

Option 3: Use open-source (Redis-cell, a Redis module)
  Integration: 1 week
  Cost: $0 licensing + $5K/year Redis hosting
  Maintenance: 2-4 hours/week (Redis upgrades, monitoring)

Decision:
  The team's core product is not rate limiting.
  Build cost is small (Redis + sliding window = well-understood).
  But maintenance cost is real ($50K/year of engineering time).
  
  At 10K req/sec: AWS WAF at $5K/year is much cheaper than the
  engineering time to build and maintain a custom solution.
  
  Recommendation: Use AWS WAF (buy) OR Redis-cell (OSS).
  Do NOT build custom unless you need features neither provides.
```

**The Stripe decision — build the payment network:**

Stripe chose to build their own payment network rather than sitting on top of existing processing networks. This was a "build" decision where building was correct because: (1) payments IS their core competency, (2) existing solutions had latency and reliability limitations that hurt their product, (3) they had the expertise, and (4) the competitive advantage from owning the stack was enormous. Most companies should NOT replicate this decision — Stripe's situation was exceptional.

**Brainstorming Questions:**
1. Your team wants to build a custom analytics pipeline. Commercial options (Segment, Amplitude) cost $50K/year. Estimate the true 3-year cost of building it yourself, including maintenance and on-call. How do you decide?
2. "Build" is sometimes described as giving you more control. Give a specific example where more control from building is genuinely valuable, and one where it's illusory (you don't actually use the control).
3. Your company uses a vendor for email delivery (SendGrid). The vendor raises prices 3× and threatens to raise them further. How do you evaluate the decision to build an in-house email delivery system?
4. A junior engineer argues: "we should build our own Kubernetes because then we control it." How would you respond? What's the counterargument, and under what (rare) circumstances might they be right?

---

## Part 6: Vendor Evaluation — What to Ask, What to Distrust

*(L4 → L5 level)*

When evaluating a commercial vendor (SaaS, PaaS), the sales process is designed to make the vendor look good. Your job is to look past the demo and understand what you're actually buying.

**The vendor evaluation checklist:**

```
BEFORE THE DEMO:
□ What is the vendor's pricing model? Is it per seat, per usage, per API call?
  (Ask for a projection at 10× your current scale)
□ What are the contract terms? Annual vs. monthly? Exit clause?
□ Who are their other customers at your scale? Can you speak to them?
□ What is their uptime SLA? What do they pay if they miss it?
  (Usually: service credits, not cash. Read the fine print.)
□ Have they had major outages in the last 12 months? (Check their status page)

DURING THE DEMO:
□ Ask: "Show me what happens when this fails."
  (Not "show me the happy path" — show me the failure behavior)
□ Ask: "Show me the logging and debugging tools available to me."
  (Can you debug problems without the vendor's help?)
□ Ask: "What was your worst incident in the last 12 months?"
  (Vendors who refuse to answer this are a red flag)
□ Ask: "What are the limitations that your biggest customers hit?"
  (Every vendor has scale walls — find out where yours are)

AFTER THE DEMO:
□ Request a 30-day free trial (or 90 days for expensive tools)
□ Run your actual workload against it, not their example workload
□ Ask for 3 reference customer contacts at your scale
□ Actually call those references (don't skip this step)
□ Have your security team review their SOC 2 report and data handling
```

**The questions vendors hate (but you should always ask):**

```
1. "What happens to our data if we cancel the contract?"
   Good answer: "You get a full export within 30 days in standard formats."
   Red flag: "Our data portability is covered in the enterprise contract."
   (Translation: you're locked in unless you pay more)

2. "What is the real p99 latency, with our data, at our volume?"
   Good answer: they run a benchmark with your data.
   Red flag: "Our average latency is X ms." (Average means nothing)

3. "What's your API deprecation policy?"
   Good answer: "We give 12 months notice before deprecating any API."
   Red flag: "We upgrade continuously." (Translation: your code may break)

4. "Show me a customer who migrated away from you. What was the migration cost?"
   This question signals: you are thinking about reversibility.
   Any vendor that can't answer this should raise your concern about lock-in.

5. "What's your pricing at 10× our current usage?"
   Good answer: they give you a number.
   Red flag: "We'd have to negotiate that." (Translation: it goes up a lot)
```

**The reference call — actually do it:**

Reference calls are the most underused part of vendor evaluation. Call 2-3 customers who use the vendor at similar scale. Ask:

```
Questions to ask vendor references:
1. "What's the worst incident you had with this vendor in the last year?"
2. "What feature would you most like them to add?"
3. "If you were evaluating again, what would you do differently?"
4. "How is their support when something breaks at 3am?"
5. "Are you planning to renew? Why?"
```

If you can't get reference contacts from the vendor, search LinkedIn for engineers at companies that use the vendor, and reach out directly.

**Red flags in vendor evaluation:**

```
🚩 Refuses to provide a trial period
🚩 Cannot answer questions about data export/portability
🚩 SLA only provides service credits, no cash compensation for downtime
🚩 Pricing is opaque or requires enterprise contract to discuss
🚩 Support is only available during business hours (no 24/7 for paid tiers)
🚩 Vendor is less than 3 years old with no clear funding beyond Series A
🚩 Status page shows > 3 incidents in the last 90 days
🚩 Their security documentation is out of date or not publicly available
```

**Brainstorming Questions:**
1. You're evaluating a database-as-a-service vendor. What 3 specific questions would you ask about data portability and migration? Why are these questions important?
2. A vendor's demo looks impressive. They show 99.99% uptime and < 5ms latency. What would you do before trusting these numbers?
3. A vendor is offering a 50% discount if you sign a 3-year contract. What are the risks of accepting? What contractual protections would you negotiate for?
4. You're on a reference call with a current customer of a vendor you're evaluating. They seem happy. What follow-up questions would you ask to find the real pain points?

---

## Part 7: Risk and Reversibility Analysis

*(L5 level)*

Every technology decision carries risk. The question is not "is this risky?" — everything is risky. The question is "what are the specific risks, how likely are they, and how do we mitigate them?"

**The risk dimensions:**

```
┌─────────────────────────────────────────────────────────────────────┐
│              TECHNOLOGY DECISION RISK DIMENSIONS                   │
├────────────────────┬────────────────────────────────────────────────┤
│  TECHNICAL RISK    │ Does it do what we need at production scale?   │
│                    │ Will it survive our edge cases?                │
│                    │ Mitigate with: PoC, load testing, reference    │
│                    │ customers at similar scale                     │
├────────────────────┼────────────────────────────────────────────────┤
│  OPERATIONAL RISK  │ Can we run this when things go wrong?          │
│                    │ Do we have the expertise?                      │
│                    │ Mitigate with: training, hiring, managed       │
│                    │ service option, clear runbooks                 │
├────────────────────┼────────────────────────────────────────────────┤
│  VENDOR RISK       │ Is the vendor stable?                          │
│                    │ What if they raise prices 10×?                │
│                    │ What if they get acquired?                    │
│                    │ Mitigate with: data portability contract,      │
│                    │ migration plan, avoiding critical path usage  │
├────────────────────┼────────────────────────────────────────────────┤
│  TEAM RISK         │ Will the team adopt this?                      │
│                    │ Will we be able to hire engineers who know it? │
│                    │ Mitigate with: team buy-in process,            │
│                    │ training, broad market adoption check          │
├────────────────────┼────────────────────────────────────────────────┤
│  REVERSIBILITY     │ If this is wrong, how painful is it to undo?  │
│                    │ Low reversibility = needs higher evidence bar. │
│                    │ Mitigate with: abstraction layer,              │
│                    │ migration plan written before adopting         │
└────────────────────┴────────────────────────────────────────────────┘
```

**The reversibility spectrum:**

```
Easy to reverse:                   Hard to reverse:
  Logging library (swap in a day)    Primary database (years of migration)
  HTTP client library                User auth system (millions of users)
  Load balancer (gradual migration)  Message queue (100 consumers coupled)
  CDN provider                       Data warehouse (TBs of historical data)
  Feature flag system                Microservice protocol (gRPC vs REST)
  
Rule: the harder to reverse, the higher the evidence bar before adopting.

For "easy to reverse": 1-2 engineers, 1-week PoC, brief doc is enough.
For "hard to reverse": full team, multi-week PoC, formal eval doc,
                        migration plan, reversibility contract.
```

**The abstraction layer as a risk mitigation:**

Sometimes you can make a hard-to-reverse decision softer by wrapping it in an abstraction:

```go
// Direct dependency (hard to reverse — every call site uses Redis directly):
redis.Set(ctx, key, value, ttl)

// Abstraction layer (easier to reverse — swap implementation, not call sites):
type Cache interface {
    Set(ctx context.Context, key string, value any, ttl time.Duration) error
    Get(ctx context.Context, key string) (any, error)
}

type RedisCache struct { client *redis.Client }
func (r *RedisCache) Set(...) error { ... }

// Now you can swap RedisCache for MemcachedCache, DynamoDBCache, etc.
// without changing any call site.
```

The trade-off: abstractions add complexity. Use them only when the reversibility benefit is worth the cost.

**The "write the migration plan before adopting" exercise:**

Before committing to a technology, write: "If in 2 years we decide to migrate away from this, here is how we would do it."

If you cannot write a plausible migration plan, you are taking on more lock-in than you may realize.

```
Example for a database evaluation:
  Migration plan from Database X to Postgres:
  1. Deploy Postgres alongside Database X
  2. Dual-write all new data to both
  3. Backfill historical data with throttled migration job
  4. Run read queries against Postgres for 2 weeks (validation)
  5. Flip read traffic to Postgres
  6. Remove Database X writes
  7. Decommission Database X
  
  Estimated migration cost: 8-12 engineer-weeks
  Data at risk: 0 (dual-write ensures consistency)
  Downtime required: 0
  
This is a reasonable migration plan. The decision has known reversibility cost.
```

**Brainstorming Questions:**
1. You're evaluating a new primary database. Rate its reversibility (easy/medium/hard to reverse). What specific factors determine the reversibility of a database choice?
2. Your team wants to adopt a vendor authentication service. Write a 3-sentence "migration plan away from this vendor" that you would include in the evaluation doc.
3. A technology has low technical risk but high vendor risk (startup, < $10M funding). How does this affect your evaluation? What contractual protections would you seek?
4. The "abstraction layer" approach reduces lock-in but adds complexity. Give an example where the abstraction is clearly worth it and one where it's clearly not worth the overhead.

---

## Part 8: Migration Cost Estimation

*(L5 level)*

Adopting a new technology usually means migrating away from the old one. The migration cost is often larger than the integration cost, and almost always larger than teams estimate.

**Why migration costs are underestimated:**

```
What engineers estimate:         What actually happens:
  "Migrate 3 services"             3 services + 7 indirect dependencies
  "1 week per service"             3 weeks each (edge cases, testing)
  "Can run migrations in parallel" Sequential: each migration blocks the next
  "Clean cutover"                  6 months of running both systems in parallel
  "Zero downtime"                  2 planned maintenance windows
  
Common multiplier: 3-5× the initial estimate.
```

**The migration cost estimation framework:**

```
STEP 1: COUNT DEPENDENCIES
  How many services call this technology directly?
  How many services depend on services that call it?
  Example: 5 direct services, 15 indirect = 20 total migrations

STEP 2: CLASSIFY DEPENDENCY TYPES
  Simple (client library swap): 1-3 days
  Complex (schema change + data migration): 1-3 weeks
  Very complex (protocol change + backfill): 1-4 months

STEP 3: IDENTIFY DATA MIGRATION
  Is there data to migrate?
  How much? (volume matters for migration time)
  Is it live data? (dual-write period required)
  Can you backfill? (or is it append-only?)

STEP 4: IDENTIFY TESTING BURDEN
  Each service needs: unit tests updated, integration tests updated,
  load tests re-run, canary deploy validated.
  Estimate: 30-50% of migration time is testing.

STEP 5: ADD BUFFER
  Always add 50% buffer for: unexpected edge cases, team availability,
  competing priorities, partial rollbacks that extend timelines.
```

**A migration cost example — migrating from MongoDB to Postgres:**

```
Current state:
  12 services use MongoDB
  4TB of data across 50 collections
  3 services have complex aggregation pipelines

Estimation:
  Phase 1: Schema design + data model translation
    - 4 weeks (50 MongoDB collections → Postgres schema)
    - 2 engineers

  Phase 2: Service migration (12 services)
    - Simple services (8): 1 week each = 8 weeks (but 4 in parallel = 2 weeks)
    - Complex aggregation services (3): 3 weeks each = 9 weeks (in parallel = 3 weeks)
    - 1 very complex service: 6 weeks
    - Total: ~11 weeks with parallelism

  Phase 3: Data migration
    - 4TB at 100MB/sec write speed = ~11 hours for bulk load
    - But: need dual-write + validation = 4-8 weeks of running both
    
  Phase 4: Testing and validation
    - Load testing: 2 weeks
    - Data consistency validation: 2 weeks
    
  Phase 5: Cutover and decommission
    - Gradual traffic shift: 2 weeks
    - Decommission MongoDB: 1 week

  Total estimate: 6-8 months, 3-4 engineers
  
  Initial team estimate was: "3 months with 2 engineers."
  True cost: more than double the initial estimate.
```

**Strategies to reduce migration cost:**

```
1. STRANGLER FIG PATTERN
   New code goes to the new system.
   Old code stays on the old system.
   Over time, the old system "dies" as code is rewritten.
   Never force a big-bang migration.

2. FEATURE FLAGS / SHADOW MODE
   New system processes all requests but results are discarded.
   Old system serves actual traffic.
   Compare new vs. old output. Validate. Then flip.
   Zero downtime. Zero data risk.

3. READ BEFORE WRITE MIGRATION
   For caches/reads: populate new system lazily (on-read) rather than
   bulk backfilling. Works when data is reproducible from source of truth.

4. DUAL-WRITE PERIOD
   Write to both old and new systems simultaneously.
   Read from old. Validate new is correct. Switch reads to new.
   Stop writing to old. Decommission.
   Cost: 2× write overhead during transition.
```

**Brainstorming Questions:**
1. Your team estimates a technology migration will take 1 month. Using the 3-5× multiplier rule, what's a more realistic estimate? What specific unknowns would you investigate to refine this?
2. The strangler fig pattern is recommended for large migrations. What are its limitations? When would it not be applicable?
3. You're migrating from a managed service to self-hosted infrastructure. What migration risks are specific to this direction (vs. managed to managed)?
4. A team says "we'll just do a big-bang cutover over a weekend." What are the risks? What would you recommend instead?

---

## Part 9: Writing the Evaluation Document

*(L5 level)*

The evaluation document is the artifact that records your reasoning, enables team review, and prevents the decision from being relitigated 6 months later.

A good eval doc has exactly one job: make the decision and the reasoning clear enough that someone who wasn't in the room can understand and trust the conclusion.

**The evaluation document template:**

```markdown
# Technology Evaluation: [What You're Evaluating]
## Status: [DRAFT / IN REVIEW / DECIDED]
## Decision date: [YYYY-MM-DD]
## Authors: [Names]
## Stakeholders: [Who reviewed and approved]

---

## 1. Problem Statement

What problem are we solving? Why now?

Example:
  Our product search is slow (p99 = 2.1s) and missing basic features
  (no typo tolerance, no faceting). This is causing measurable checkout
  abandonment. We need a solution before the holiday season in 3 months.

---

## 2. Requirements

### Must-haves (disqualifying if not met)
- p99 search latency < 200ms at 1,000 QPS
- Support 10M indexed products
- Go and Python SDKs
- GDPR-compliant (data can be hosted in EU)

### Nice-to-haves (scored 1-5)
- Typo correction
- Faceting and filtering
- Multi-language support
- Managed service option (no ops burden)
- Real-time index updates (< 5s lag)

---

## 3. Options Evaluated

| Option        | Type          | Cost/year | PoC done? |
|---------------|---------------|-----------|-----------|
| Elasticsearch | OSS + managed | ~$24K     | Yes       |
| Typesense     | OSS + managed | ~$8K      | Yes       |
| Algolia       | SaaS          | ~$60K     | No (demo) |
| Build custom  | Internal      | ~$100K    | N/A       |

---

## 4. Evaluation Results

### Must-haves scorecard
| Requirement          | Elasticsearch | Typesense | Algolia |
|----------------------|---------------|-----------|---------|
| p99 < 200ms at 1KQPS | ✅ 95ms       | ✅ 87ms   | ✅ 60ms |
| 10M products         | ✅            | ✅        | ✅      |
| Go + Python SDKs     | ✅            | ✅        | ✅      |
| GDPR (EU hosting)    | ✅            | ✅        | ✅      |

All three meet must-haves. Build custom eliminated (cost and timeline).

### Nice-to-haves scorecard (1-5)
| Feature              | Elasticsearch | Typesense | Algolia |
|----------------------|---------------|-----------|---------|
| Typo correction      | 4             | 5         | 5       |
| Faceting             | 5             | 4         | 5       |
| Multi-language       | 5             | 3         | 4       |
| Managed service      | 4             | 5         | 5       |
| Real-time updates    | 3             | 4         | 5       |
| **Total**            | **21/25**     | **21/25** | **24/25**|

### Cost comparison (3-year TCO)
| Option        | Annual cost | 3-year TCO |
|---------------|-------------|------------|
| Elasticsearch | $24K + ~$30K ops | $162K |
| Typesense     | $8K + ~$10K ops  | $54K  |
| Algolia       | $60K + ~$5K ops  | $195K |

---

## 5. PoC Findings

PoC question: "Can Typesense serve our catalog search at 1,000 QPS with
< 200ms p99, with typo correction and faceting?"

Result: Yes. Details:
  - p99 latency: 87ms at 1,000 QPS (well under 200ms target)
  - Typo correction: works correctly for product name searches
  - Faceting: 6 simultaneous facets at < 100ms
  - Index update lag: 30-60 seconds (acceptable for catalog, not inventory)

---

## 6. Risks

| Risk                      | Likelihood | Impact | Mitigation                          |
|---------------------------|-----------|--------|-------------------------------------|
| Typesense startup failure | Low       | High   | Contractual data export clause      |
| Scale beyond PoC          | Low       | Medium | Re-evaluate at 50M products         |
| 60s index lag for catalog | Medium    | Low    | Inventory shown separately (live DB)|

---

## 7. Recommendation

**Adopt Typesense (managed)**

Reasoning: Typesense meets all must-haves. Cost is 3× cheaper than Algolia
and 3× cheaper than Elasticsearch (when ops burden is included). The only
risk is startup viability — mitigated by contractual data export clause.
The 60s index lag is acceptable for product catalog (products change slowly).

---

## 8. Decision and Next Steps

Decision: [APPROVED / REJECTED / DEFERRED]
Approvers: [Names, dates]

Next steps:
1. Finalize Typesense contract with data portability clause (Week 1)
2. Begin integration in payment-service (Week 2-3)
3. Canary deploy to 5% of search traffic (Week 4)
4. Full rollout (Week 6)
5. Decommission old search implementation (Week 8)
```

**What makes a good eval doc:**

```
✅ States the problem before the options (don't lead with "we're evaluating X vs Y")
✅ Shows the criteria were defined before options were evaluated
✅ Includes data from actual testing (PoC results, reference customer calls)
✅ Is honest about trade-offs (no option is perfect — say what each option lacks)
✅ Separates must-haves from nice-to-haves (clear disqualification criteria)
✅ Includes risk assessment with mitigations
✅ States a clear recommendation (don't hedge — say what you'd do)
✅ Lists next steps so it's clear who does what after the decision
```

**Brainstorming Questions:**
1. You finish writing an eval doc recommending Technology A. A senior engineer disagrees and prefers Technology B. What should happen next? How does a good eval doc help resolve this?
2. What's the difference between an eval doc and a design doc (RFC)? When would you write each?
3. An eval doc from 2 years ago is referenced to justify a technology choice. You think the recommendation might be outdated. What process would you follow to revisit it?
4. You're an engineer reviewing someone else's eval doc. What are the 3 most important things you check to validate the quality of the evaluation?

---

## Part 10: Getting Buy-In and Handling Disagreement

*(L5 → L6 level)*

Writing a great eval doc is necessary but not sufficient. Technology decisions involve people, and people have preferences, biases, and careers invested in specific technologies. Getting buy-in is a skill as important as the evaluation itself.

**Why buy-in matters:**

```
Without buy-in:
  The eval doc is approved, but engineers on the team resent the decision.
  They build workarounds. They don't maintain it well.
  They say "I told you so" at the first sign of trouble.
  The technology fails not because it's bad, but because it wasn't supported.
  
With buy-in:
  Engineers understand WHY the decision was made.
  They commit to making it work even when it's hard.
  They advocate for it to future joiners.
  Problems get reported and fixed, not hidden and avoided.
```

**The buy-in process:**

```
1. INVOLVE STAKEHOLDERS EARLY
   Don't evaluate in secret, then announce the decision.
   Invite affected engineers to define the criteria.
   "What are your requirements for the new queue system?"
   They feel heard. The criteria are better. Buy-in is higher.

2. SHARE DRAFTS, NOT FINAL DECISIONS
   Send the eval doc as "draft for review" before the decision is made.
   Gives people a chance to raise concerns while the decision is still open.
   "Here's what we found. Does this match your understanding?
    Are we missing any criteria?"

3. ADDRESS TECHNICAL OBJECTIONS WITH DATA
   When someone disagrees: "What data would change your mind?"
   If the answer is "nothing" — it's a preference, not a technical concern.
   If the answer is something testable — run the test and show the result.

4. ESCALATE DISAGREEMENTS EXPLICITLY
   Don't let disagreements fester.
   "We have two camps: some prefer X, some prefer Y. The reasons are [A, B, C].
    We need to make a decision by [date]. If we can't reach consensus, [manager]
    will make the call."
   Setting a decision deadline forces resolution.

5. DOCUMENT THE DECISION, NOT JUST THE RECOMMENDATION
   Record WHO decided, WHEN, and WHY.
   When someone challenges the decision 6 months later:
   "Here's the eval doc. Here's who approved it. Here are the criteria.
    If you think the criteria were wrong, let's discuss the criteria —
    not relitigate the decision."
```

**Handling "but Company X uses Technology Y" arguments:**

This is the most common form of technology enthusiasm that bypasses evaluation. How to handle it:

```
Engineer: "Netflix uses Kafka for everything. We should use Kafka."

Response:
  "Netflix processes 700 billion events per day with teams of 10+
   platform engineers dedicated to Kafka operations.
   
   We process 10K events per day and have 1 engineer with Kafka experience.
   
   The criteria we need to evaluate against are:
   1. Can we operate it reliably? (High risk for us)
   2. Does it solve our actual problem? (What IS our problem exactly?)
   3. What's the cost at our scale? (Likely overkill)
   
   Let's define our requirements first, then evaluate Kafka AND simpler
   alternatives like SQS or RabbitMQ against those requirements.
   
   If Kafka wins on the criteria, we'll use Kafka. If not, we won't."
```

**Brainstorming Questions:**
1. You recommend Technology A in an eval doc, but 3 senior engineers prefer Technology B. The eval data favors A, but the discussion is getting heated. How do you facilitate a productive resolution?
2. A "tech lead" on another team has already announced they're using Technology X and expects your team to follow. You have concerns. What's your process?
3. Why is "we should use what the team already knows" both a valid argument AND a potentially dangerous one? When should familiarity override an evaluation result?
4. After a technology decision is made, someone who disagreed keeps raising concerns. How do you balance "respecting disagreement" with "moving forward efficiently"?

---

## Part 11: Named Real-World Technology Decisions

*(L5 level — named examples for interview credibility)*

**Decision 1: GitHub's migration from Resque to Sidekiq (2013)**

GitHub used Resque (Ruby job queue) for background jobs. As GitHub grew, Resque's limitations became clear: no concurrency within a process, poor monitoring. They evaluated Sidekiq (also Ruby, but multi-threaded). The criteria: concurrent job processing, same Redis backend, backward compatible with existing jobs, better monitoring. Sidekiq won. The migration was incremental — new jobs went to Sidekiq, old jobs stayed on Resque. Full migration took 6 months. Lesson: backwards compatibility and incremental migration paths make large-scale tech migrations feasible.

**Decision 2: Uber's evaluation of Go for their microservices (2015-2016)**

Uber's Node.js services were hitting CPU limits and having GC pause issues at scale. They evaluated Go vs. Java vs. staying with Node.js. Criteria: performance, concurrency model, operational simplicity, team ramp-up time. Go won: better performance than Node.js for CPU-bound work, simpler concurrency model than Java (goroutines), fast compile times, static binary (easy to deploy). The evaluation was documented in an internal RFC that compared production metrics from PoC services. Lesson: performance criteria must be measured against your specific workload, not synthetic benchmarks.

**Decision 3: Discord switching from Cassandra to ScyllaDB (2022-2023)**

Discord stored 4 billion messages in Cassandra but experienced latency spikes (p99 = 40-125ms) due to Cassandra's garbage collection. They evaluated migrating to ScyllaDB — a Cassandra-compatible database written in C++ (no GC). The PoC ran both Cassandra and ScyllaDB in parallel for months on a shadow of production traffic. Result: p99 latency dropped from 40ms to 15ms. The migration was possible because ScyllaDB speaks the Cassandra CQL protocol — application code was unchanged. Lesson: API compatibility reduces migration risk dramatically; evaluate "drop-in replacement" options before assuming a full rewrite.

**Decision 4: Figma's choice to build on AWS vs. multi-cloud (2019)**

Figma evaluated whether to be multi-cloud (AWS + GCP) or single-cloud (AWS only). The criteria: operational simplicity, feature availability (Figma uses some AWS-specific real-time services), cost, and portability risk. They chose single-cloud (AWS). Reasoning: multi-cloud is 2-3× more operationally complex, limits which managed services you can use, and the "portability" benefit is theoretical (nobody actually migrates away from AWS without a major incident driving it). Lesson: portability is a real benefit but has a real cost — evaluate it against the likelihood you'll actually need it.

**Decision 5: Notion's migration from MongoDB to Postgres (2021)**

Notion outgrew MongoDB's consistency and transaction guarantees. They needed strong ACID transactions for collaborative editing (two users editing the same page simultaneously must not corrupt data). The eval criteria: ACID transactions, horizontal scaling path, operational maturity, team expertise. Postgres won. The migration took 18 months and 3 engineers to execute. They wrote a detailed public postmortem. Key technique: shadow mode — all writes went to both MongoDB and Postgres; they compared results for correctness before cutting over reads. Lesson: data migrations take much longer than expected; always budget 3-5× your initial estimate.

---

## Part 12: L5 vs. L6 Calibration

```
┌────────────────────────────────────────────────────────────────────────────────┐
│          L3 / L4 / L5 / L6 TECHNOLOGY EVALUATION CALIBRATION                 │
├──────────────┬─────────────────────────────────────────────────────────────────┤
│  L3 (SWE)    │ Evaluates two specific tools for a specific task.              │
│              │ Writes a comparison doc (pros/cons list).                      │
│              │ Picks the one the team lead seems to prefer.                  │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L4 (SSE)    │ Defines requirements before looking at options.               │
│              │ Runs a time-boxed PoC with a specific question.               │
│              │ Evaluates build vs. buy. Writes a basic eval doc.             │
│              │ Can recommend a choice and give reasons.                       │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L5 (Sr SWE) │ Runs full structured evaluation:                              │
│              │   criteria → options → PoC → TCO → risk → recommendation      │
│              │ Does vendor evaluation (reference calls, contract review).     │
│              │ Estimates migration cost accurately.                           │
│              │ Writes eval doc that enables async review and decision.        │
│              │ Gets buy-in from skeptical stakeholders.                       │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L6 (Staff)  │ Designs the org's evaluation process.                         │
│              │ Decides which decisions need formal eval vs. judgment call.    │
│              │ Runs evaluations that span multiple teams.                     │
│              │ Makes "platform" decisions (the tech that all teams adopt).    │
│              │ Writes the criteria for criteria — "how should we think        │
│              │ about build vs. buy at this company?"                          │
│              │ Influences vendor relationships (negotiates enterprise terms). │
│              │ Creates the organization's technology radar.                   │
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

**The technology radar:**

An L6/Staff-level artifact: a living document that categorizes technologies by maturity and recommended adoption status for the organization.

```
ADOPT:    Proven, recommended for all new projects.
          Example: Go (primary language), Postgres (relational DB),
                   Kubernetes (orchestration), Prometheus (metrics)

TRIAL:    Promising, use with care in non-critical paths.
          Example: Temporal (workflow orchestration), ClickHouse (OLAP)
          
ASSESS:   Interesting, worth watching. Not ready to recommend.
          Example: new database X, emerging protocol Y
          
HOLD:     Avoid in new projects. Migrate away from existing usage.
          Example: MongoDB (replaced by Postgres), Cassandra (legacy)
```

---

## Part 13: Pre-Interview Drill — 10 Questions

**Q1: How would you approach evaluating a new technology for your team?**

"I follow a structured approach: first define the problem we're solving and what 'winning' looks like as measurable criteria — separating must-haves (disqualifying) from nice-to-haves. Then identify candidate options. For the top 2-3 candidates, run a time-boxed PoC (1-2 weeks) answering one specific question about our hardest requirement. Calculate 3-year TCO for each option. Assess risks and reversibility. Write an eval doc with the recommendation. Socialize for review before deciding."

**Q2: How do you decide between building something in-house vs. buying a commercial solution?**

"I start with: does a commercial solution solve 80%+ of our requirements? If yes, I calculate the full 3-year TCO — buy cost (subscription + integration) vs. build cost (initial + annual maintenance + on-call). I also ask: is this our core competency? If no, buy unless the cost is prohibitive. Finally: what's the reversibility cost? High lock-in requires higher confidence. The 'build' option is usually underestimated by 3-5× — include ops, monitoring, security patches, and on-call in the estimate."

**Q3: What should a technology evaluation PoC answer?**

"A PoC answers one specific question: 'Can this technology do X for our specific use case at our scale?' Not 'is this technology generally good?' Not 'let's build the real integration.' The PoC should be time-boxed (1-2 weeks), use production-like data, test the worst-case scenario (not the happy path), and produce a clear binary conclusion: yes or no."

**Q4: What's the most important thing to check when evaluating a vendor?**

"Data portability and migration path. What happens to our data if we cancel? Can we export in standard formats? What's the migration plan if we need to switch vendors? I also check: reference customers at similar scale (and actually call them), pricing at 10× current usage, and their worst incident in the last 12 months. Vendors who are opaque about these signals have something to hide."

**Q5: How do you estimate the cost of migrating from one technology to another?**

"I count the number of direct and indirect dependencies. Classify them by complexity (simple client swap = 1-3 days, schema migration = 1-3 weeks). Add: data migration time (volume matters), dual-write period for live data, testing burden (30-50% of migration time), and 50% buffer for unknowns. The most common mistake is forgetting indirect dependencies and the testing burden. Typical actual cost: 3-5× initial estimate."

**Q6: How do you handle a team member who strongly disagrees with your technology recommendation?**

"I start by asking: 'What data would change your mind?' If the answer is something testable, I run the test. If the answer is 'nothing,' it's a preference, not a technical objection. I document the disagreement in the eval doc — 'some team members prefer Y because [reason]; this was evaluated and rejected because [data].' If we can't reach consensus, I escalate with a clear deadline: 'We'll discuss until [date], then [decision maker] will decide.' I don't let disagreements block the decision indefinitely."

**Q7: What is reversibility and why does it matter in technology decisions?**

"Reversibility is how difficult and expensive it is to undo a technology decision in 2-3 years. A logging library is easy to reverse (swap in a day). A primary database is hard to reverse (months of migration work). Hard-to-reverse decisions need a higher evidence bar before adopting. I always ask: 'If this is wrong in 2 years, how do we migrate away?' If I can't write a plausible migration plan, I'm taking on more lock-in than I realize."

**Q8: How do you write a technology evaluation document?**

"The eval doc structure: (1) problem statement — why does this decision need to be made, (2) requirements — must-haves and nice-to-haves, defined before evaluating options, (3) options evaluated — what candidates were considered and quickly dismissed, (4) evaluation results — scorecard against criteria, TCO comparison, PoC findings, (5) risks and mitigations, (6) recommendation — clear and direct, not hedged, (7) decision record — who approved, when, next steps."

**Q9: When should you NOT do a formal technology evaluation?**

"When the decision is low-stakes and easily reversible (choosing between two logging libraries), when the team has strong consensus and the choice is clearly correct (picking Postgres for a relational use case in 2026), or when time pressure is extreme and the cost of delay exceeds the cost of a slightly suboptimal choice. Formal evaluation is for high-impact, high-reversibility-cost, or high-disagreement decisions."

**Q10: Tell me about a technology decision you drove.**

"SOAR format: at [company], our search was hitting scaling limits with basic SQL LIKE queries (Situation). I was asked to evaluate search options for our product catalog (Task). I defined 5 measurable criteria: latency < 200ms at 1K QPS, 10M products, Go SDK, typo correction, managed service. Ran PoCs on Elasticsearch and Typesense. Typesense scored equally on functionality at 1/3 the TCO ($18K vs $54K/year). Wrote the eval doc, got team buy-in, shipped in 6 weeks. Result: search latency from 1.8s to 87ms p99, checkout abandonment decreased 8%."

---

## Part 14: Exercises

**Exercise 1: Evaluate a technology you use daily**

Pick a technology your current team uses (a database, a message queue, a monitoring tool). Retroactively apply the evaluation framework. Write: what were the likely criteria when it was chosen? Does it still meet those criteria today? What would you choose if you were evaluating it fresh?

**Exercise 2: Define criteria before looking at options**

You need a task queue for a background job processing system. Before Googling any options: write 5 measurable must-have criteria and 3 nice-to-have criteria. Then evaluate AWS SQS, RabbitMQ, and Redis-based queues against your criteria. Did your criteria help narrow the choice?

**Exercise 3: PoC scope exercise**

You're evaluating a new caching layer (Redis vs. Memcached). Write the PoC plan: the specific question the PoC answers, the time box, the data you'll use, what you will and won't build, and the criteria for "success" and "failure."

**Exercise 4: Write a mini eval doc**

Choose any technology decision your team faces or has recently made. Write a 1-page eval doc using the template from Part 9. Include: problem statement, 3 must-haves, 2 nice-to-haves, 2 candidate options scored, recommendation with reasoning.

---

## Part 15: Homework

**Reading:**
- Thoughtworks Technology Radar (thoughtworks.com/radar) — read how a world-class firm evaluates and categorizes technologies. Pay attention to the "Hold" entries — why did previously-adopted technologies get demoted?
- Notion's "Migrating Notion's data lake" blog post — a real migration war story from a respected engineering team.
- "Build vs Buy" by a16z (search for it) — a VC perspective on when startups should build vs. buy infrastructure.

**At your current job:**
- Find a technology decision your team made in the last 12 months. Ask: was there a written evaluation? If yes, read it. If no, reconstruct: what criteria would have been used? Is the decision still the right one today?
- For any upcoming technology decision on your team (no matter how small): try writing the criteria before looking at options. Notice how it changes the conversation.

**Research:**
- Read Discord's "How Discord Stores Trillions of Messages" and their Cassandra → ScyllaDB migration post. Write a 3-sentence summary of their evaluation criteria and decision rationale.
- Find 2 "we built X in-house and regret it" or "we migrated from X to Y and here's why" engineering blog posts. What pattern do you notice in the reasoning?

---

## Part 16: Vocabulary Quick Reference

```
PoC (Proof of Concept):  Time-boxed experiment answering one specific question.
                          NOT a prototype, NOT a demo.

TCO (Total Cost of Ownership): Full cost over a time period including licensing,
                                 integration, operations, maintenance, and migration.

Must-have criteria:      Requirements that disqualify a candidate if not met.
                          Evaluated before nice-to-haves.

Nice-to-have criteria:   Desired features scored to differentiate candidates
                          that all pass must-haves.

Reversibility:           How easily a technology decision can be undone.
                          High lock-in = lower reversibility.

Strangler Fig:           Migration pattern: new code uses new system, old code
                          stays on old system until it's all replaced. No big-bang.

Dual-write:              Write to both old and new systems simultaneously
                          during migration. Read from old until new is validated.

Technology radar:        Org-level document categorizing technologies by adoption
                          status: Adopt / Trial / Assess / Hold.

Vendor lock-in:          Dependency on a vendor's proprietary APIs/formats
                          that makes switching expensive.

Safepoint bias:          (See Ch122 — Java profiler term; listed here for reference)

Reference customer:      Existing customer of a vendor at similar scale who
                          you call to validate the vendor's claims.
```

---

## Memorable Quotes

> *"The best technology is the one your team can operate at 3am. The second best is the one that solves your actual problem."*

> *"Build only what you cannot buy. Operate only what you cannot delegate. Optimize only what you have measured."*

> *"Technology decisions are usually not reversible on a comfortable timeline. Spend 4 weeks evaluating something you'll live with for 4 years."*

> *"A PoC that confirms what you already believed is not a PoC. It's theater."*

> *"Define your criteria before you fall in love with a candidate."*

---

---

## Part 17: The Evaluation Anti-Patterns

*(All levels — the traps to avoid)*

Great engineers make technology decisions well. But even experienced engineers fall into recognizable anti-patterns. Knowing these by name lets you recognize and call them out early.

**Anti-pattern 1: Resume-Driven Development (RDD)**

Definition: choosing a technology because it looks impressive on a resume, not because it's the right fit for the problem.

```
Signal: "Let's use [trendy tech]. It'll be great experience for the team."
         "I want to learn [new tech]. This is a good opportunity."
         
Why it happens:
  Engineers advance their careers partly through technical exposure.
  Choosing "boring" but appropriate technology feels like a missed opportunity.
  Using exciting technology feels like career growth.

Why it's harmful:
  The company's codebase is not an engineer's learning sandbox.
  Adopting inappropriate technology has real operational costs — forever.
  "Learning opportunity" benefits fade in 6 months; maintenance costs last 6 years.

Counter-move:
  Ask explicitly in evaluation: "What is the business reason for this choice?"
  Separate "good for the company" from "good for my resume."
  Both can be true. But they should be stated separately.
```

**Anti-pattern 2: Analysis Paralysis**

Definition: evaluating indefinitely because the "perfect" answer hasn't emerged yet.

```
Signal: "Let's just run one more PoC."
         "I want to talk to 3 more reference customers."
         "Let's wait for the next major version to stabilize."

Why it happens:
  Decision-makers fear being wrong.
  The consequences of a bad decision feel very permanent.
  More research always feels safer than deciding.

Why it's harmful:
  You're running the current system (which you know is inadequate) longer.
  The opportunity cost of delay is real.
  Perfect information is never available — decisions must be made under uncertainty.

Counter-move:
  Set a decision date before starting the evaluation.
  Define upfront: "After PoC, we will have enough information to decide."
  Document: "We are accepting these remaining uncertainties."
```

**Anti-pattern 3: The Sunk Cost Fallacy**

Definition: continuing to use a technology that's clearly inadequate because "we've already invested so much in it."

```
Signal: "We can't migrate away — we've spent 2 years on this."
         "We just need to make it work harder."

Why it happens:
  Admitting a past decision was wrong feels like personal failure.
  The migration cost seems greater than it is (vs. ongoing inefficiency cost).
  Nobody wants to be the one who "wasted" the previous investment.

Why it's harmful:
  Each additional year on the wrong technology compounds the migration cost.
  The sunk cost is gone regardless. Evaluate from "what's best going forward."
  
Counter-move:
  Frame migration decisions as: "Given where we are today, what's the best
  path forward?" — not "was the original decision right?"
  Calculate: cost of staying on current tech for 2 more years vs. migration cost.
  This often shows migration is cheaper.
```

**Anti-pattern 4: Evaluating in Secret**

Definition: doing the evaluation without involving the people who will be affected.

```
Signal: One engineer builds a PoC and presents the decision as fait accompli.
         "I've already decided we're using X. Now I'm writing the eval doc."

Why it happens:
  Moving fast feels more efficient than consensus-building.
  Engineers sometimes fear that involving others will slow decisions.
  "I've already evaluated this — I know it's right."

Why it's harmful:
  People who weren't consulted don't feel ownership over the decision.
  They spot failure modes you didn't see (that's why you involve them).
  Buy-in is much harder to get after a decision is announced as final.

Counter-move:
  Define criteria with stakeholders before evaluating options.
  Share the draft eval doc before the decision is final.
  Ask: "What am I missing?" — and mean it.
```

**Anti-pattern 5: Ignoring Operational Cost**

Definition: evaluating technical capability while ignoring the operational burden.

```
Signal: "Kafka supports our throughput!" (ignores: do we know how to run Kafka?)
         "The PoC showed excellent performance!" (ignores: who's on-call for this?)

Why it happens:
  Engineers are good at evaluating functionality and performance.
  Operational burden is harder to quantify.
  The engineers evaluating won't be the ones on-call at 3am.

Counter-move:
  Add an explicit operational criteria category.
  Ask: "If this breaks at 3am, who would debug it? Do they know how?"
  Ask: "What is the on-call runbook? Does it exist?"
  Ask: "How has this technology behaved for others at similar scale?"
```

**Brainstorming Questions:**
1. You notice a colleague proposing a technology that seems driven by RDD rather than real requirements. How do you raise this without attacking their motivation?
2. Your evaluation has been going on for 6 weeks and the team is still debating. What concrete steps would you take to force a resolution?
3. You joined a team that's clearly using the wrong database (it's slow, doesn't support needed queries, requires constant workarounds). The team says "we've invested too much to change it." How do you frame the conversation to move past the sunk cost fallacy?
4. Which of these five anti-patterns is most common in your current organization? What enables it?

---

## Part 18: The Lightweight Evaluation — When You Don't Need a Full Process

*(L4 → L5 level)*

Not every technology decision needs a 4-week evaluation, a PoC, vendor reference calls, and a formal eval doc. Over-engineering the evaluation process is its own form of waste. The skill is knowing when to apply rigor and when to move quickly.

**The decision size matrix:**

```
                    HIGH REVERSIBILITY       LOW REVERSIBILITY
                  ┌─────────────────────────┬──────────────────────────┐
HIGH IMPACT       │ Quick eval + doc         │ Full evaluation required │
(affects many     │ 1-2 week PoC             │ Criteria + PoC + vendor  │
 services or      │ Team discussion          │ + TCO + risk + eval doc  │
 long-lived)      │                          │ + buy-in process         │
                  ├─────────────────────────┼──────────────────────────┤
LOW IMPACT        │ Just decide              │ Quick eval + document    │
(local, one       │ Team consensus           │ No PoC needed            │
 service, short-  │ No formal doc needed     │ Write the rationale      │
 lived decision)  │                          │ in a Slack thread        │
                  └─────────────────────────┴──────────────────────────┘

Examples by quadrant:

HIGH impact, HIGH reversibility:
  → Monitoring tool (can swap in a few weeks)
  → Logging library (can swap across services over time)
  → Do a quick eval + lightweight doc. PoC if uncertain.

HIGH impact, LOW reversibility:
  → Primary database for a new product
  → Message queue as core platform infrastructure
  → Auth system
  → Full evaluation: criteria + PoC + vendor calls + eval doc

LOW impact, HIGH reversibility:
  → HTTP client library
  → CSV parsing library
  → Test assertion library
  → Just decide. Team consensus. No doc needed.

LOW impact, LOW reversibility:
  → Internal CLI tool framework
  → Code generation tool for a specific service
  → Write a brief rationale in a PR description.
  → No full eval doc, but record the reasoning.
```

**The 1-hour evaluation:**

For small decisions, use a structured 1-hour format instead of a full process:

```
1. Write 3 requirements (10 minutes)
   What specifically does this tool need to do?

2. Find 2-3 options (15 minutes)
   Quick Google/documentation review.
   Eliminate non-starters immediately.

3. Pick the one that fits best (5 minutes)
   Which option meets all 3 requirements with the least complexity?

4. Record in Slack or PR comment (10 minutes)
   "We chose X over Y because [1 sentence]. Risks: [1 sentence]."
```

Total: 40 minutes. Decision made. Reasoning recorded.

**When lightweight evaluation is inappropriate:**

```
NOT lightweight when:
  - The decision affects more than 2 services
  - The migration cost if wrong exceeds 4 weeks of engineering time
  - The technology will be on the critical path (user-facing, revenue-critical)
  - The team has low confidence (nobody has used this technology before)
  - The vendor relationship is significant (multi-year contract, high cost)
```

**Brainstorming Questions:**
1. You're evaluating a new JSON parsing library for a single internal service. Apply the decision size matrix. What level of evaluation is appropriate?
2. Your team adopted a technology using the "just decide" approach and it turned out to be a poor fit. How do you improve the process without adding excessive overhead?
3. What's the minimum documentation you'd require for any technology decision, regardless of its size? (There's a floor below which "we discussed it in Slack" is insufficient.)
4. A new engineer on your team asks: "How do I know when a decision needs a formal eval doc?" What 3 criteria would you give them?

---

## Part 19: The Technology Decision in a System Design Interview

*(Interview preparation — L5 context)*

Technology evaluation isn't just a work skill — it shows up in system design interviews. When an interviewer says "what database would you use?", they're testing whether you evaluate systematically or pick by instinct.

**The wrong answer pattern:**

```
Interviewer: "What database would you use for this system?"

Weak answer: "I'd use Postgres because I know it well."
             "I'd use Cassandra because Netflix uses it for high scale."
             "I'd use MongoDB because it's flexible."

Why these are weak:
  - No mention of requirements or constraints
  - No mention of trade-offs
  - No mention of why this database vs. alternatives
  - "I know it well" is not a technical justification
  - "Company X uses it" ignores that your constraints differ from Company X
```

**The strong answer pattern:**

```
Interviewer: "What database would you use for this system?"

Strong answer:
  "Let me think about the access patterns and constraints first.
   
   [From the design context:]
   - Read-heavy (10:1 read/write ratio)
   - Queries by user_id and timestamp (sorted range scans)
   - 1TB of data, growing 100GB/year
   - Consistency: eventual is fine (feed data, not financial)
   - Team is strong on Postgres, no Cassandra experience
   
   Given those constraints, I'd consider two main options:
   
   Option 1: Postgres with time-based partitioning
     - Good: team expertise, ACID transactions, flexible queries
     - Concern: need partitioning strategy for 1TB+
     - Mitigated by: partition by month, archive old partitions to S3
   
   Option 2: Cassandra
     - Good: excellent for time-series write scaling, built for this pattern
     - Concern: team has no Cassandra experience, high operational complexity
     - Mitigated by: use managed service (Astra DB) to reduce ops burden
   
   Given the team's expertise and the scale (1TB, not 100TB), I'd recommend
   Postgres with partitioning. The operational simplicity outweighs Cassandra's
   scale advantage at this data volume. We can re-evaluate when we approach
   10TB."
```

**The key interview moves:**

```
1. STATE CONSTRAINTS BEFORE OPTIONS
   "Given the read-heavy workload, consistency requirements of X,
   and scale of Y, I'd consider..."

2. NAME 2 OPTIONS AND TRADE-OFFS
   Never say just one option. Always compare.
   Interviewers want to see you know the trade-off space.

3. MAKE A RECOMMENDATION WITH REASONING
   "I'd go with A over B because [specific reason tied to constraints]."
   Don't hedge with "it depends" without being specific.

4. ACKNOWLEDGE UNCERTAINTY
   "If the scale turned out to be 100× larger, I'd revisit Cassandra."
   This shows you're thinking about edge cases, not just the happy path.

5. MENTION OPERATIONAL REALITY
   "The team has strong Postgres expertise, which matters because..."
   Operational considerations are valid in interviews. They're valid in real life.
```

**Common system design database questions and evaluation framework:**

```
"Design a Twitter-like feed system"
  Key constraints: write-heavy (millions posts/day), read-heavy (timeline),
  fan-out pattern (follow relationships), soft real-time
  
  Candidates to evaluate: Cassandra (fan-out, time-series), Redis (cache/fan-out),
  Postgres (core data), Kafka (event streaming for fan-out)
  
  Evaluation angle: Cassandra for timeline storage (high write throughput,
  time-series partitioning by user+date), Redis for hot timelines (cache),
  Postgres for user/follow graph (relational).

"Design a rate limiter"
  Key constraints: low latency (< 1ms), high throughput, distributed,
  sliding window or token bucket algorithm
  
  Candidates: Redis (atomic counters, fast, built-in TTL), custom (full control),
  Memcached (simpler, less features)
  
  Evaluation angle: Redis wins — atomic INCR operations, TTL, distributed,
  1ms latency. Building custom only if Redis can't serve the needed algorithm.
  
"Design a notification system"
  Key constraints: reliable delivery (at-least-once), delayed delivery support,
  high fan-out (send to 10M users), multiple channels (push, email, SMS)
  
  Candidates: Kafka (reliable, scalable), SQS (managed, simpler), RabbitMQ (less scale)
  
  Evaluation angle: Kafka for internal event stream (10M fan-out);
  SQS for per-channel delivery queues (managed, simpler);
  Twilio/SendGrid for external delivery (buy, not build).
```

**Brainstorming Questions:**
1. In a system design interview, you're asked "why did you pick Postgres over MongoDB?" Write a 3-sentence answer that demonstrates evaluation thinking.
2. An interviewer challenges your database choice: "But Cassandra handles much higher scale." How do you respond in a way that shows confident reasoning without being dismissive of their point?
3. When should you mention "I'd do a PoC to validate this" in a system design interview? When would it sound like evasion vs. genuine engineering discipline?
4. You've confidently picked a technology in your system design. 10 minutes later, new constraints emerge that make you doubt the choice. How do you handle this gracefully?

---

## Part 20: War Stories — Decisions That Define Companies

*(Named incidents — L5 interview credibility)*

**War Story 1: Amazon's move to microservices (2002)**

Jeff Bezos issued the infamous "API mandate": every team must expose their data through service interfaces, with no direct database sharing. At the time, Amazon was a monolith. The technical evaluation was: should we refactor the monolith, or re-architect around services? The decision criteria were operational independence (teams blocking each other) and scalability (the monolith couldn't scale different parts differently). The microservices choice was made. Cost: enormous, multi-year rewrite. Benefit: it became the foundation for AWS. The evaluation was forced by operational pain, not by theoretical architectural purity. Lesson: sometimes the "big" technology decision is forced by an organizational problem, not a technical one.

**War Story 2: Dropbox's "Exodus" — leaving AWS for their own hardware (2016)**

Dropbox ran on AWS for years. In 2016, they moved to their own data centers in a project called "Exodus." The evaluation: at Dropbox's scale (exabytes of storage), the economics of owning hardware vs. paying AWS became favorable. Their specific calculation: over 2 years, they would save ~$75M in infrastructure costs. The PoC: they ran hybrid (own hardware + AWS) for 18 months to validate. The decision was specifically for storage (their largest cost) — they kept running on AWS for services that weren't storage-bound. Lesson: build vs. buy decisions can flip as scale grows; what's correct at 100TB may be wrong at 1 exabyte.

**War Story 3: Slack rebuilding their message storage (2016)**

Slack's original message storage was a MySQL cluster. As Slack grew to billions of messages, MySQL hit limits: slow full-text search, slow bulk history loads, increasing latency on user-facing queries. They evaluated: shard MySQL further, migrate to Cassandra, or build a custom solution. Their evaluation criteria: full-text search, bulk loading (Slack export feature), per-channel read history, and write throughput. They ended up with a custom solution built on a combination of Lucene (search) and MySQL (data storage with improved schema). The key insight: no off-the-shelf solution met all their criteria (especially search + bulk export combination). Build was justified. Lesson: the "build" option is sometimes right — but only after thoroughly proving no existing solution meets your requirements.

**War Story 4: Figma's choice of PostgreSQL at scale (2022)**

Figma is a real-time multiplayer design tool. Their core data model — design documents with real-time collaboration — needed strong consistency. At launch, they used Postgres. As Figma grew to millions of documents and hundreds of concurrent editors, they faced the question: do we scale Postgres or migrate to a distributed database? Their evaluation: Cassandra and DynamoDB both lack the transaction guarantees they needed (multiple tables updated atomically in collaborative operations). They chose to scale Postgres vertically and horizontally through pgBouncer (connection pooling), read replicas, and careful partitioning — rather than migrate to a distributed database. Lesson: "boring" technology (Postgres) can scale further than expected with the right operational practices; don't migrate to a distributed system before you've exhausted your current system's limits.

**War Story 5: Twitter's move from Ruby on Rails to JVM (2012-2015)**

Twitter was originally built on Ruby on Rails. As Twitter grew to millions of tweets/day, Ruby's performance characteristics (GIL, dynamic typing overhead, GC pauses) created bottlenecks. They evaluated: optimize Ruby further, migrate to JVM (Scala/Java), or use Python. The decision criteria: throughput (Ruby was hitting CPU limits), latency (GC pauses causing p99 spikes), and concurrency model (Ruby's GIL limits multi-core utilization). Scala won: JVM performance, functional programming style the team preferred, and good ecosystem. The migration was a multi-year effort — hundreds of Rails services rewritten as JVM services. Lesson: language/runtime decisions are high reversibility cost (massive migration) — make them with extreme care.

---

## Part 21: Calibration by Company Stage

*(Applies to how rigorously you should evaluate)*

Technology evaluation looks different depending on company stage. What's appropriate at a 10-person startup is overkill. What's appropriate at a 10,000-person company is dangerous at a startup.

```
┌──────────────────────────────────────────────────────────────────────────┐
│            EVALUATION RIGOR BY COMPANY STAGE                           │
├──────────────┬───────────────────────────────────────────────────────────┤
│  SEED/SERIES │ Speed matters more than optionality.                     │
│  A STARTUP   │ Use boring, well-known technologies. Postgres, Redis,    │
│  (< 30 eng)  │ RabbitMQ. Don't evaluate — just use what works.         │
│              │ Exception: core differentiator (your product's magic     │
│              │ feature). Evaluate that carefully. Everything else:      │
│              │ pick and move on.                                        │
├──────────────┼───────────────────────────────────────────────────────────┤
│  SERIES B/C  │ Now you're hitting real scale. Decisions made at 10     │
│  GROWTH      │ engineers are pinching at 100.                          │
│  (30-200 eng)│ Lightweight evaluation for most decisions.              │
│              │ Full evaluation for: primary data stores, platform       │
│              │ infrastructure, anything that will run 50+ services.    │
├──────────────┼───────────────────────────────────────────────────────────┤
│  LARGE TECH  │ Full evaluation for any cross-team decision.            │
│  (200+ eng)  │ Technology radar for organization-wide guidance.        │
│              │ Platform team owns evaluation of foundational infra.    │
│              │ Individual teams do evaluation for domain-specific tools.│
│              │ Formal eval doc required before migrating any system    │
│              │ that > 5 teams depend on.                               │
└──────────────┴───────────────────────────────────────────────────────────┘
```

**The startup technology bias:**

At a startup, default to technologies with these properties:
1. **Your team knows them** — operational expertise matters more at small scale
2. **Large community** — when you hit an edge case, StackOverflow has the answer
3. **Proven at your scale** — don't run Cassandra for 10K messages/day
4. **Good managed service options** — you don't have infra engineers; buy managed
5. **Easy to hire for** — Postgres engineers are everywhere; [obscure DB] engineers aren't

**Brainstorming Questions:**
1. You join a 15-person startup that's using Kafka, Kubernetes, and Elasticsearch in production. Is this a problem? What would you investigate to find out?
2. Your growth-stage company (150 engineers) is about to pick a data warehouse. This decision will affect all analytics for 5+ years. What level of evaluation rigor is appropriate?
3. A large company's platform team wants to mandate a single message queue for all 200 services. How is this decision different from a team-level technology evaluation?
4. A startup founder says "we're going to use [new and trendy tech X]." You're the first engineering hire. How do you evaluate whether to push back on this choice?

---

## Appendix A: The Evaluation Checklist

A printable quick-reference for running any technology evaluation.

```
BEFORE YOU START
□ Write the problem statement (what are we solving?)
□ Set a decision deadline
□ Identify who needs to be consulted (define early)
□ Classify the decision (size × reversibility) → decide on evaluation depth

CRITERIA DEFINITION
□ List requirements in each category: functional, performance, operational,
  ecosystem, risk
□ Mark each as must-have or nice-to-have
□ For must-haves: define the specific pass/fail threshold
□ Review criteria with stakeholders before evaluating options

OPTIONS IDENTIFICATION
□ List all plausible candidates (including "build" and "do nothing")
□ Quickly eliminate non-starters against must-haves
□ Continue with top 2-3 candidates

POC (if applicable)
□ Write the PoC question before writing any code
□ Time-box: set start and end date
□ Use production-like data
□ Test worst case, not happy path
□ Document the result: yes/no + supporting data

VENDOR EVALUATION (if applicable)
□ Get pricing at 10× current scale
□ Call 2 reference customers
□ Ask the "questions vendors hate"
□ Review data portability terms
□ Check status page (last 90 days incidents)

COST ANALYSIS
□ Calculate 3-year TCO for each finalist
□ Include integration cost, ops cost, on-call burden
□ Apply 3-5× multiplier to any build cost estimate

RISK AND REVERSIBILITY
□ Write the migration plan away from each option
□ Rate reversibility: easy / medium / hard
□ Identify the top 3 risks + mitigations

WRITING THE DOC
□ Problem statement (not "we're evaluating X vs Y")
□ Requirements (criteria defined before evaluation)
□ Options considered (include quick eliminations + reasoning)
□ Evaluation results (scorecard + PoC findings + TCO)
□ Risks and mitigations
□ Recommendation (clear, direct, not hedged)
□ Decision record (approvers, date, next steps)

BUY-IN
□ Shared doc with stakeholders before decision is final
□ Addressed technical objections with data
□ Documented dissenting opinions in the doc
□ Set a decision deadline and escalation path if needed
```

---

---

## Appendix B: Common Technology Categories and Evaluation Angles

This section gives you starting points for evaluating specific classes of technology. Each category has its own most-important criteria.

**Databases (relational)**

Primary question: What are the access patterns — point lookups, range scans, aggregations, joins?

```
Must-haves to always check:
  - ACID transactions (do you need them? For financial data: yes. For analytics: no)
  - Horizontal scaling strategy (read replicas, sharding, partitioning)
  - Backup and restore (RTO/RPO — how fast can you recover from data loss?)
  - Connection pooling story (Postgres needs pgBouncer or equivalent at scale)
  - Migration tooling (Flyway, Liquibase — how do you change schema in production?)

Differentiation criteria:
  - JSON support (Postgres JSONB vs MySQL JSON — Postgres wins)
  - Full-text search built-in (Postgres tsvector)
  - Window functions, CTEs (Postgres stronger than MySQL historically)
  - Time-series extensions (TimescaleDB for Postgres)
```

**Message queues / event streaming**

Primary question: At-most-once, at-least-once, or exactly-once delivery semantics? What's the message retention need?

```
Must-haves:
  - Delivery guarantee (at-least-once vs exactly-once)
  - Consumer groups / competing consumers pattern support
  - Dead-letter queue (what happens to messages that fail repeatedly?)
  - Retention period (Kafka keeps messages; SQS deletes after consumption)

Differentiation:
  - Replay (Kafka yes; SQS no — affects event sourcing patterns)
  - Throughput (Kafka: millions/sec; SQS: 3,000/sec standard queue)
  - Managed service quality (SQS is mature, AWS-managed; MSK is Kafka-managed-ish)
  - Fan-out (SNS→SQS vs Kafka consumer groups vs Pulsar subscriptions)
```

**Caches**

Primary question: Is this a read cache (reduce DB load) or a session store or a distributed lock?

```
Must-haves:
  - Eviction policy support (LRU, LFU, TTL)
  - Cluster mode (if you need > 1 node for reliability or capacity)
  - Persistence (Redis AOF/RDB if you need durability; Memcached is volatile-only)
  - Atomic operations (Redis INCR, SETNX for distributed locks)

Differentiation:
  - Data structures (Redis: strings, hashes, lists, sets, sorted sets, streams)
                    (Memcached: strings only — simpler but less flexible)
  - Lua scripting (Redis) — enables atomic multi-step operations
  - Pub/sub (Redis) vs. Memcached (none)
  - Memory efficiency at scale (Memcached is simpler and sometimes more
    memory-efficient for pure key-value use cases)
```

**Search engines**

Primary question: Is this full-text search, faceted search, or semantic/vector search?

```
Must-haves:
  - Relevance model (BM25 + field boosting minimum; vector search if ML-powered)
  - Index update latency (how quickly do writes appear in search results?)
  - Query language complexity (can your team write/debug the queries needed?)

Differentiation:
  - Typo tolerance (Typesense/Meilisearch excellent; Elasticsearch configurable)
  - Multi-tenancy (Elasticsearch indices per tenant; Typesense collections)
  - Vector search support (Elasticsearch, OpenSearch, Qdrant, Pinecone)
  - Operational complexity (Typesense/Meilisearch << Elasticsearch for ops burden)
```

**Observability (metrics, logs, traces)**

Primary question: What's your team's operational maturity and how much do you want to own?

```
Must-haves:
  - Metrics collection and alerting (Prometheus + AlertManager or hosted equivalent)
  - Log aggregation and search (Loki, Elasticsearch, Splunk, Datadog)
  - Distributed tracing (Jaeger, Zipkin, Tempo, Datadog APM)

Differentiation:
  - Managed vs. self-hosted cost (Datadog: expensive at scale; Grafana stack: cheap)
  - Cardinality limits (high-cardinality labels → cost in Datadog; OOM in Prometheus)
  - OpenTelemetry compatibility (future-proofs against vendor lock-in)
  - On-call alert quality (Datadog's alerting UI is polished; Prometheus requires
    configuration work to get to the same quality)
```

---

## Appendix C: Evaluation in Remote / Async Teams

Technology decisions in distributed teams need extra process because organic buy-in (hallway conversations, whiteboard sessions) doesn't happen naturally.

**Async evaluation best practices:**

```
1. WRITE THE PROBLEM STATEMENT ASYNC-FIRST
   Not: "Let's schedule a meeting to discuss our search options."
   Yes: "I've written a problem statement doc. Please comment by EOW."
   
   The written problem statement forces clarity before any conversation.
   People in other timezones can engage before any meeting happens.

2. ASYNC CRITERIA DEFINITION
   Share a criteria list in a doc. Ask people to +1 or add criteria.
   Run this async for 2-3 days before any synchronous discussion.
   By the time you meet, the criteria are already 80% defined.

3. RECORD THE DECISION CALL
   Any synchronous decision meeting should be recorded.
   People who couldn't attend can review. People who weren't sure they
   understood can re-watch.

4. DECISION LOG IN THE DOC
   The final eval doc should have: decision date, decision maker, all
   stakeholders who reviewed, and a "dissenting opinions" section.
   This is especially important async: people may not be able to voice
   objections synchronously.

5. ANNOUNCE DECISIONS BROADLY
   "We decided X. Here's the doc. Comments close [date]."
   Give a brief window for final input before the decision is fully locked.
   This isn't reversibility — it's last-call courtesy.
```

---

## Appendix D: Frameworks Mentioned in This Chapter

Quick reference — the named frameworks used throughout, with sources.

```
MUST / SHOULD / NICE (MoSCoW method)
  Origin: DSDM (Dynamic Systems Development Method), Dai Clegg, 1994
  Use: classifying requirements by priority
  
RICE Scoring
  Origin: Intercom product management framework
  Use: prioritizing features (Reach, Impact, Confidence, Effort)
  Note: adapted here for technology evaluation scoring

Thoughtworks Technology Radar
  Origin: Thoughtworks (technology consulting firm), published biannually
  Use: organization-level technology categorization (Adopt/Trial/Assess/Hold)
  Access: thoughtworks.com/radar (public, free)

Strangler Fig Pattern
  Origin: Martin Fowler (2004)
  Use: incremental migration from old system to new without big-bang cutover

Total Cost of Ownership (TCO)
  Origin: Gartner (1987)
  Use: full cost analysis including all direct and indirect costs over time
```

---

---

## Final Thought: Evaluation Is a Habit, Not an Event

The engineers who make consistently good technology decisions don't evaluate harder — they evaluate more often. They build the habit of:

- Asking "what do we need?" before "what should we use?"
- Writing down decisions even when they seem obvious
- Revisiting old decisions when context changes
- Treating migration cost as a design constraint, not an afterthought

Start small. The next time your team is about to pick a library or a tool, take 30 minutes to write 3 requirements before looking at options. Notice how much cleaner the conversation becomes. That habit — small as it is — is the foundation of every technology decision in this chapter.

The frameworks in this chapter scale from a 1-hour decision to a 6-month platform evaluation. The core skill — defining requirements before evaluating options, measuring against evidence — is the same at every scale.

Most engineers get better at building systems. The best engineers also get better at choosing which systems to build, which to buy, and which to avoid entirely. That discernment is what separates L5 from L6.

---

## Exercises

**Exercise 1 — Build/buy/OSS decision.** For each scenario, choose build, buy (managed SaaS), or use open-source — and justify: (a) internal analytics dashboard, (b) authentication system for a product with 10M users, (c) distributed tracing, (d) message queue for a startup with 3 engineers. What's the primary criterion for each?

**Exercise 2 — Evaluation criteria definition.** You're evaluating three search engines (Elasticsearch, Typesense, Meilisearch). Before looking at any feature list, write the 6 evaluation criteria that matter for your use case. Rank them by importance. Then evaluate each candidate against your criteria — not theirs.

**Exercise 3 — POC scope definition.** You want to evaluate a new database. Design a POC: what specific questions must the POC answer, how long should it run, what data do you test with, who reviews the results, and what outcome triggers "proceed" vs. "reject"?

**Exercise 4 — Total cost of ownership.** Evaluate managed Kafka (Confluent Cloud at $0.50/GB) vs. self-hosted Kafka (3 brokers, your ops team manages). Model: your current data volume (50GB/day), projected growth (3x/year), engineering hours for self-hosted maintenance (estimate), and ops cost. Which is cheaper at what scale?

**Exercise 5 — Reversibility assessment.** You're choosing a new ORM. Evaluate reversibility: how hard is it to switch in 2 years if you're unhappy? What's the migration path? How much of your codebase would be affected? Use this to adjust your decision weight toward or away from this option.

**Exercise 6 — Reference check design.** You've shortlisted two message queue options. Design the reference check process: who do you talk to (engineers at other companies using these in production), what questions do you ask (failure modes, operational burden, scaling pain points, what they'd do differently), and how you weight anecdotal vs. benchmark evidence.

---

## Homework

**Assignment 1 — Technology decision retrospective.** Pick a technology your team adopted in the last 2 years. Write a retrospective: what criteria drove the decision, what you got right, what you got wrong, and what you'd do differently knowing what you know now.

**Assignment 2 — Current decision POC.** Identify a technology decision your team needs to make in the next quarter. Write the evaluation criteria and POC plan before anyone starts looking at vendor websites. Share for team alignment.

**Assignment 3 — Interview practice: technology choice question.** Practice "which database would you choose for a real-time leaderboard, and why?" in 5 minutes. Cover: your evaluation criteria, two candidates considered, why one wins, and what would change your answer.

**Assignment 4 — Read "Build vs. Buy" (Martin Fowler on bliki).** Write a one-paragraph summary of the core argument and connect it to a technology decision your team is currently facing.

*Pairs with [Chapter 111: Migrations and Safe Changes](Chapter_111_Migrations_and_Safe_Changes.md) and [Chapter 116: Refactoring Large Systems](Chapter_116_Refactoring_Large_Systems.md). Next: [Chapter 124: Technical Roadmapping and Engineering Strategy](Chapter_124_Technical_Roadmapping_and_Engineering_Strategy.md).*

---

*Pairs with [Chapter 111: Migrations and Safe Changes](Chapter_111_Migrations_and_Safe_Changes.md) (technology decisions create migrations) and [Chapter 116: Refactoring Large Systems](Chapter_116_Refactoring_Large_Systems.md) (refactoring often involves technology evaluation). Next: [Chapter 124: Technical Roadmapping and Engineering Strategy](Chapter_124_Technical_Roadmapping_and_Engineering_Strategy.md).*