# Serverless: When and Trade-offs

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Taking a taxi vs owning a car. Car: you pay even when it's parked. Insurance. Loan. Garage. Server: you pay even when it's idle. CPU ticks. Memory reserved. Taxi: you pay only when riding. No maintenance. No parking. Just pay per trip. Serverless is the taxi. Your code runs only when triggered. No servers to manage. Auto-scales to zero and to infinity. Pay per invocation. But: cold starts, limited execution time, vendor lock-in. Let's unpack it.

---

## The Story

Serverless doesn't mean "no servers." It means *you* don't manage them. The cloud provider runs your code in response to events. HTTP request? Lambda runs. New file in S3? Lambda runs. Message in a queue? Lambda runs. You write a function. Deploy it. That's it. No EC2. No Kubernetes. No SSH. No "how many instances?"

The model: event in, function runs, response out. Stateless. Each invocation can run on a different container. Scale? Automatic. 0 requests? 0 cost (mostly). 10,000 requests? 10,000 concurrent executions. No provisioning. No capacity planning. Ideal for spiky, unpredictable load.

Trade-offs. **Cold start**: first request (or after idle) spins up a container. 100ms to a few seconds. Latency spike. **Execution limit**: AWS Lambda max 15 minutes. Long batch jobs? Not ideal. **Vendor lock-in**: your code runs on Lambda's runtime. Different providers have different APIs. **Debugging**: harder. No server to SSH into. Logs and traces are your tools. **Cost**: at low volume, cheap. At high volume, might be more expensive than always-on servers. Do the math.

**Stateless:** Functions must be stateless. No in-memory session. Each invocation can hit a fresh container. Store state in DB, cache, or pass in the request. This constraint shapes design. Often good—forces clean separation of compute and state.

**Hybrid:** You don't have to go full serverless. Mix. API Gateway + Lambda for low-traffic endpoints. EC2 or ECS for the hot path. Best of both. Use the right tool per use case. Serverless for webhooks, cron, event triggers. Servers for steady, latency-sensitive workloads.

**Monitoring:** No server to SSH into. Logs and metrics are everything. CloudWatch, Datadog, etc. Log every invocation. Track cold starts, duration, errors. Set alarms. Serverless obscures the machine. Observability becomes your eyes. Invest in it early. Distributed tracing: each invocation gets a trace ID. Follow it across services. Essential for debugging in a serverless world. Serverless is a paradigm shift. Embrace its constraints. They often lead to better, more modular design.

---

## Another Way to See It

Think of a food truck vs a restaurant. Restaurant: rent, staff, kitchen—always paid. Even with zero customers. Food truck: park when no customers. Open when someone shows up. Pay for gas and ingredients when you serve. Serverless is the food truck. Run when needed. Park (scale to zero) when not.

Or a gym. Traditional: monthly membership. You pay whether you go or not. Serverless: pay-per-visit. Go once, pay once. Don't go, pay nothing. Perfect if you're inconsistent. Expensive if you go every day.

---

## Connecting to Software

Serverless fits: webhooks, APIs with spiky traffic, file processing (S3 trigger), scheduled jobs (cron), event-driven pipelines. AWS Lambda, Google Cloud Functions, Azure Functions. Often paired with API Gateway (HTTP → Lambda), S3 (file → Lambda), SQS (message → Lambda).

Keep functions small. Single responsibility. Cold start is per function. Heavy dependencies? Slow cold start. Use layers for shared libs. Consider provisioned concurrency for latency-sensitive APIs—keeps some instances warm.

---

## Let's Walk Through the Diagram

```
    TRADITIONAL (Always-On Server)              SERVERLESS (Event-Triggered)

    Request ──► [Server Always Running]         Request ──► [API Gateway]
                        │                               │
                        │  Pay 24/7                     ▼
                        │                       [Lambda] ← spins up on demand
                        │                               │
                        ▼                               │  Pay per invocation
                   Response                             ▼
                                                   Response

    Cost: $X/month regardless of traffic        Cost: $Y per million requests
    Scale: you provision                         Scale: auto 0 to millions
```

---

## Real-World Examples (2-3)

**Example 1: Slack.** Many backend tasks are serverless. Incoming webhooks. File processing. Scheduled digest emails. Spiky. Unpredictable. Lambda-style functions. They don't need servers running 24/7 for these. Pay per use.

**Example 2: Image resize on upload.** User uploads image to S3. S3 triggers Lambda. Lambda resizes, creates thumbnails, stores in another bucket. No server running. Only runs when uploads happen. Perfect fit.

**Example 3: Airbnb.** Some APIs use serverless. Low traffic endpoints. A/B test infrastructure. Spiky. Scale to zero when not needed. Main booking flow? Maybe not—latency matters. But plenty of use cases fit.

---

## Let's Think Together

**When should you avoid serverless?**

When you need low, consistent latency. Cold starts hurt. When you have long-running jobs (hours). Lambda has a 15-min limit. When you have steady, high traffic. Always-on server might be cheaper. When you need to avoid vendor lock-in. Serverless APIs are provider-specific. Consider Kubernetes with Knative or OpenFaaS for portability.

**Can you eliminate cold starts?**

Partially. Provisioned concurrency keeps some instances warm. Costs more. Or use a "warming" strategy: ping your function every 5 minutes. Hacky. Or accept cold start for non-critical paths. First request slower. Others fast. Trade-off.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup puts their entire API on Lambda. Great at first. Low cost. Then they grow. 10 million requests per day. Lambda cost: $500/day. They do the math. Same workload on 5 EC2 instances: $50/day. They migrate. Painful. Lesson: serverless isn't always cheaper at scale. Model your costs. Traffic pattern matters. Spiky = serverless wins. Steady high = consider servers.

---

## Surprising Truth / Fun Fact

AWS Lambda was inspired by a 2014 conference talk. The team asked: what if we ran your code without you thinking about servers? Launched 2014. Now billions of invocations per day. The "serverless" term was coined around 2012. It stuck. Today it's a pillar of cloud architecture—but not a silver bullet. Right tool, right job.

---

## Quick Recap (5 bullets)

- **Serverless** = code runs only when triggered. No server management. Auto-scale. Pay per invocation.
- Good for: spiky traffic, webhooks, file processing, scheduled jobs, event-driven pipelines.
- Trade-offs: cold starts (latency), execution time limits (e.g., 15 min), vendor lock-in, cost at high scale.
- Keep functions small. Single responsibility. Use layers for shared dependencies.
- At very high, steady traffic, always-on servers may be cheaper. Model before you commit.

---

## One-Liner to Remember

Serverless = taxi, not car. Pay when you ride. No maintenance. But cold starts and limits apply. Use it when the fit is right.

---

## Next Video

Next up: **API Gateway: What It Does**—the hotel concierge between clients and your microservices. One point of contact. Routes everything.
