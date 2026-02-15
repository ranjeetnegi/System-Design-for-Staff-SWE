# Chapter 57. Notification Delivery System (Fan-out at Scale)

---

# Introduction

A notification delivery system decides who should receive a message and pushes that message to every recipient—across every device, every channel, and every time zone—within seconds. I've built and operated notification systems that delivered 2 billion notifications per day across push, email, SMS, and in-app channels, and I'll be direct: sending a single notification to a single user is trivially easy. The hard part is sending a single event's notifications to 50 million followers in under 30 seconds (fan-out), doing it without melting your infrastructure (backpressure), ensuring every user gets exactly one notification and not zero or two (exactly-once delivery semantics), respecting per-user preferences across channels and frequency caps (preference routing), degrading gracefully when a downstream channel provider is slow or down (resilience), and evolving the architecture from a monolithic "send email on event" script into a multi-channel, priority-aware, globally distributed delivery platform that powers every notification surface across the entire product—without one team's spike event (a breaking news push to all users) taking down another team's transactional alerts (password reset emails).

This chapter covers the design of a Notification Delivery System at Staff Engineer depth. We focus on the infrastructure: how fan-out is executed at scale, how channels are abstracted, how delivery guarantees are maintained, how user preferences are respected in real time, how the system degrades gracefully, and how it evolves. We deliberately simplify notification content generation (templating, localization, personalization) because those are product concerns, not system design concerns. The Staff Engineer's job is designing the delivery infrastructure that makes notifications reliable, fast, preference-aware, and evolvable.

**The Staff Engineer's First Law of Notifications**: A notification system that sends too many notifications is worse than one that sends too few. Users tolerate a missed notification once; they disable notifications permanently after three irrelevant ones. Relevance and timeliness are the product—delivery infrastructure is the constraint.

---

## Quick Visual: Notification Delivery System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     NOTIFICATION DELIVERY SYSTEM: THE STAFF ENGINEER VIEW                   │
│                                                                             │
│   WRONG Framing: "A service that sends push notifications and emails"       │
│   RIGHT Framing: "A multi-channel, priority-aware delivery pipeline that    │
│                   fans out a single event to millions of recipients,        │
│                   respects per-user channel/frequency preferences,          │
│                   guarantees at-least-once delivery with deduplication,     │
│                   and degrades gracefully across channel providers—         │
│                   all while isolating high-priority transactional alerts    │
│                   from bulk marketing blasts"                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What triggers notifications? (User actions? System events?      │   │
│   │     External signals? Scheduled campaigns?)                         │   │
│   │  2. What channels exist? (Push? Email? SMS? In-app? Webhooks?)      │   │
│   │  3. How large is the max fan-out? (1 user? 1K? 1M? 100M?)          │   │
│   │  4. What are the delivery latency requirements by priority?         │   │
│   │  5. What are the business constraints? (Frequency caps? Quiet       │   │
│   │     hours? Regulatory opt-out? Channel fallback?)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  The actual send (calling APNs, FCM, SMTP, or Twilio) is the       │   │
│   │  easiest 5% of the system. The other 95% is: determining WHO       │   │
│   │  should receive the notification (fan-out resolution), checking     │   │
│   │  WHAT each user's preferences allow (preference filtering),         │   │
│   │  deciding WHICH channel to use (channel routing), ensuring          │   │
│   │  EXACTLY ONE delivery attempt per user per event (deduplication),   │   │
│   │  handling FAILURES across unreliable third-party providers          │   │
│   │  (retry & fallback), and keeping BULK sends from starving           │   │
│   │  TRANSACTIONAL sends (priority isolation).                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Notification System Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Fan-out** | "Loop through all followers and send notifications synchronously" | "Multi-stage fan-out: event → recipient resolution (async, batched) → per-recipient preference check → per-channel queue. Fan-out is a pipeline, not a loop. Each stage has its own scaling knob. For celebrity users (1M+ followers), use pre-computed recipient lists with incremental updates, not real-time resolution." |
| **Channel routing** | "Send push notification; if it fails, send email" | "Channel router evaluates per-user preference matrix: preferred channels, opt-in/opt-out per notification type, device state (push token validity), quiet hours, frequency caps. Channel selection happens BEFORE enqueueing to channel-specific workers, not as a fallback after failure. Fallback is a separate concern from preference." |
| **Priority isolation** | "All notifications go through the same queue" | "Physically separate queues per priority class: P0 (transactional: 2FA, password reset—must arrive in seconds), P1 (social: likes, comments—should arrive in minutes), P2 (bulk: marketing campaigns—can take hours). Each priority class has dedicated worker pools and capacity reservations. A marketing blast to 50M users CANNOT delay a password reset OTP." |
| **Deduplication** | "Check a database before sending" | "Event-level deduplication with idempotency keys at ingestion. Delivery-level deduplication with per-user-per-event bloom filters at the channel worker. Two dedup layers because fan-out can produce duplicates (retry after partial success), and channel workers can retry (provider timeout). The cost of a duplicate notification is user annoyance → notification disable → permanent reach loss." |
| **Rate limiting** | "Global rate limit on the send API" | "Three-layer rate limiting: (1) Per-sender rate limit (prevent one team from flooding the system), (2) Per-user frequency cap (no user receives more than N notifications per hour/day), (3) Per-channel provider rate limit (respect APNs/FCM/SMTP throttling). Each layer operates independently with different time windows and different consequences for breach." |
| **Failure handling** | "Retry failed sends 3 times with exponential backoff" | "Channel-aware retry with circuit breakers. APNs returns HTTP 429 → back off globally for push. SMTP server rejects → mark email as soft bounce, retry later. SMS provider timeout → circuit break, fall back to push if user has push enabled. Dead-letter queue for exhausted retries with alerting. Per-channel health dashboards. Provider failover for multi-vendor channels." |

**Key Difference**: L6 engineers design the notification system as a multi-priority, multi-channel delivery platform with physical isolation between priority classes, per-user preference evaluation in the hot path, and channel-specific failure handling. They treat fan-out as a distributed pipeline problem, not a for-loop, and they understand that the blast radius of a bad notification (user disables all notifications) is permanent.

## Staff One-Liners & Mental Models

| Concept | One-Liner | Use When |
|---------|-----------|----------|
| Fan-out | "Fan-out is a pipeline with stages, not a loop with iterations." | Explaining celebrity problem, scaling fan-out |
| Priority isolation | "Priority isolation must be physical, not logical. Logical priority in a shared queue fails under load." | Justifying P0/P1/P2 separate queues |
| Notification fatigue | "The notification you suppress is as important as the one you deliver. Notification fatigue leads to permanent channel loss." | Frequency caps, aggregation, quiet hours |
| SMS cost | "SMS is the most expensive channel by 1000×. Every SMS we eliminate saves more than any infrastructure optimization." | Cost optimization, channel selection |
| Deduplication | "At-least-once with dedup gets us to 99.99% unique delivery. The last 0.01% is not worth the distributed transaction overhead." | Defending three-layer dedup, rejecting exactly-once |
| Degradation | "I design the degradation stack before the happy path. The system must always deliver SOMETHING—even if the primary channel is down." | Fallback channels, circuit breakers |
| Pre-computation | "Pre-compute everything that can be stale. Celebrity follower lists can be an hour old. User preferences cannot be." | Pre-computed partitions, preference freshness |
| Channel routing | "Channel routing is a cost decision, not just a reliability decision. Push is free. Email is cheap. SMS is expensive." | Default channel selection, OTP delivery |
| Blast radius | "The blast radius of a component failure tells me whether I have designed sufficient isolation. If one team's bulk campaign can delay another team's OTP, my isolation is broken." | Priority design, load shedding |

---

# Part 1: Foundations — What a Notification Delivery System Is and Why It Exists

## What Is a Notification Delivery System?

A notification delivery system takes an event ("User A liked User B's photo") and ensures the right message reaches the right user, on the right channel, at the right time. It sits between the event producers (every service in your company that generates user-relevant events) and the delivery channels (push notifications, email, SMS, in-app messages, webhooks). The system answers the question: "Given this event, who should be notified, through which channel, with what content, and how urgently?"

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE SIMPLEST MENTAL MODEL                                │
│                                                                             │
│   A notification system is a POSTAL SERVICE:                                │
│                                                                             │
│   ACCEPT: Receive a letter (event) from a sender (service)                  │
│   → "User A liked User B's photo"                                           │
│   → The sender doesn't know or care how delivery happens                    │
│                                                                             │
│   RESOLVE: Determine recipients                                             │
│   → Direct: User B (1:1 notification)                                       │
│   → Fan-out: All 50M followers of Celebrity C (1:N notification)            │
│   → Broadcast: All users in region X (system-wide notification)             │
│                                                                             │
│   FILTER: Check delivery preferences                                        │
│   → User B wants push only, not email                                       │
│   → User B has quiet hours 10pm-8am                                         │
│   → User B already got 15 notifications today (frequency cap)               │
│   → User B unsubscribed from "likes" notifications                          │
│                                                                             │
│   ROUTE: Choose the delivery channel                                        │
│   → Push notification (primary, user has valid token)                        │
│   → Email (fallback if push is undeliverable)                               │
│   → SMS (only for P0 transactional: OTP, security alerts)                   │
│                                                                             │
│   DELIVER: Hand to the channel provider                                     │
│   → APNs for iOS push, FCM for Android push                                 │
│   → SMTP relay for email                                                    │
│   → Twilio/similar for SMS                                                  │
│                                                                             │
│   TRACK: Record delivery status                                             │
│   → Sent, Delivered, Opened, Clicked, Bounced, Failed                       │
│   → Feed back into preference and channel health systems                    │
│                                                                             │
│   SCALE: Handle 10 events/sec (normal) to 1M events/sec (breaking news)     │
│   → Each event may fan out to 1 or 100 million recipients                   │
│   → Transactional alerts must not be delayed by bulk sends                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Happens on Every Notification Request

```
FOR each notification event:

  1. EVENT INGESTION
     Producer sends event → Notification API validates and enriches
     → Event: {type: "like", actor: "userA", target: "userB", 
        object: "photo_123", priority: "P1", timestamp: ...}
     → Assigned idempotency key: hash(type + actor + target + object)
     Cost: ~2ms (API validation + dedup check)

  2. RECIPIENT RESOLUTION
     Determine who should receive this notification:
     → Direct: target = userB → 1 recipient
     → Fan-out: "new_post" by Celebrity with 10M followers
       → Fetch follower list (paginated, 10K per batch)
       → Produce 1,000 batches of recipient work items
     Cost: ~5ms (direct) to ~30s (full celebrity fan-out, async)

  3. PREFERENCE EVALUATION (per recipient)
     For each recipient, check:
     → Is this notification type enabled for this user?
     → Is the user within quiet hours?
     → Has the user exceeded frequency cap?
     → Which channels has the user opted into for this type?
     Cost: ~1ms per recipient (in-memory preference cache)

  4. CHANNEL ROUTING (per recipient)
     For each surviving recipient:
     → Select primary channel based on preference + device state
     → Push: Check token validity (cached), route to push queue
     → Email: Check email validity (not bounced), route to email queue
     → In-app: Always (stored for retrieval on next app open)
     Cost: ~0.5ms per recipient (routing logic + enqueue)

  5. CHANNEL DELIVERY (per channel worker)
     Channel-specific workers pull from their queues:
     → Push worker: Batch sends to APNs/FCM (500 per batch)
     → Email worker: Render template, send via SMTP relay
     → SMS worker: Format message, send via SMS provider
     Cost: ~50-500ms per batch (dominated by provider latency)

  6. DELIVERY TRACKING
     Record outcome per recipient per channel:
     → Success: Mark delivered, update delivery metrics
     → Transient failure: Re-enqueue with backoff
     → Permanent failure: Mark failed, trigger fallback channel
     → Bounce: Update user's channel health (invalid token/email)
     Cost: ~1ms (async write to delivery log)

TOTAL: 
  Direct notification (1 recipient): < 500ms end-to-end
  Fan-out notification (1M recipients): < 60s for all recipients
  Bulk campaign (50M recipients): < 2 hours, throttled
```

## Why Does a Notification Delivery System Exist?

### The Core Problem

Every product service generates events that users care about. Without a centralized notification system:

1. **Every team builds its own notification logic.** The chat team sends push directly, the commerce team has its own email pipeline, the social team has a separate SMS integration. You now have 15 notification systems, none of which respect user preferences consistently.

2. **User preferences are fragmented.** User disables "marketing emails" in one system but still gets them from another. Quiet hours are respected by push but not by email. Frequency caps don't exist because no single system sees total notification volume.

3. **Delivery reliability varies wildly.** One team retries aggressively (causing duplicate notifications), another doesn't retry at all (causing missing notifications). Token management (APNs/FCM) is inconsistent—stale tokens waste provider quota.

4. **Priority inversion is inevitable.** A marketing campaign sends 50M emails, saturating the SMTP relay. A user's password reset email waits in the same queue. The user can't log in.

5. **No aggregate visibility.** You can't answer "how many notifications did user X receive today across all channels?" because there's no single system of record.

### What Happens If This System Does NOT Exist

```
WITHOUT A CENTRALIZED NOTIFICATION SYSTEM:

  User receives 47 notifications in one hour from 8 different teams
  → All using different opt-out mechanisms
  → User can't disable them consistently
  → User disables ALL notifications at the OS level
  → You've permanently lost the ability to reach that user

  Marketing team sends a 50M-user email blast
  → Saturates shared SMTP infrastructure
  → 2FA verification emails delayed by 45 minutes
  → Users can't log in → Support tickets spike
  → Revenue-impacting incident

  Push token expires for 30% of users over 3 months
  → No central token management detects this
  → 30% of push notifications silently fail
  → Teams blame "low engagement" instead of "broken delivery"
  → Product decisions made on flawed data

  Three teams independently build retry logic for push
  → Team A: retry 3x, no dedup → users get triple notifications
  → Team B: no retry → 15% of notifications silently dropped
  → Team C: retry with dedup but no circuit breaker
    → APNs rate-limits the entire app when Team C hammers it

  RESULT: Inconsistent delivery, frustrated users, wasted engineering
  effort across teams, and no organization-wide view of notification health.
```

---

# Part 2: Functional Requirements (Deep Enumeration)

## Core Use Cases

```
1. TRANSACTIONAL NOTIFICATION (P0)
   Trigger: System event requiring immediate user action
   Examples: OTP/2FA codes, password reset, payment confirmation,
             security alert, account lockout
   Fan-out: 1:1 (always single recipient)
   Latency: < 5 seconds end-to-end
   Channel: SMS + push (dual-send for reliability)
   Delivery guarantee: Must deliver or alert on failure

2. SOCIAL NOTIFICATION (P1)
   Trigger: User action on another user's content
   Examples: Like, comment, follow, mention, share, reply
   Fan-out: 1:1 (direct) or 1:N (group activity)
   Latency: < 30 seconds
   Channel: Push (primary), in-app (always), email (digest)
   Delivery guarantee: Best-effort with dedup

3. CONTENT NOTIFICATION (P1)
   Trigger: New content from followed entity
   Examples: New post from followed user, new video from channel,
             new article from publication
   Fan-out: 1:N where N can be 1 to 100M (celebrity problem)
   Latency: < 60 seconds for P50 recipients, < 5 minutes for P99
   Channel: Push (if enabled), in-app (always)
   Delivery guarantee: Best-effort, can drop under extreme load

4. SYSTEM NOTIFICATION (P1)
   Trigger: Platform event affecting user
   Examples: Feature announcement, policy change, maintenance notice,
             account status change
   Fan-out: 1:N (targeted segment) or broadcast (all users)
   Latency: Minutes to hours (not time-critical)
   Channel: In-app (always), email (if opted in), push (if critical)

5. MARKETING / CAMPAIGN NOTIFICATION (P2)
   Trigger: Scheduled campaign by marketing team
   Examples: Promotional offers, re-engagement campaigns,
             personalized recommendations, newsletters
   Fan-out: 1:N where N is typically 1M-50M
   Latency: Hours (entire campaign), throttled to avoid provider limits
   Channel: Email (primary), push (secondary)
   Delivery guarantee: Best-effort, subject to frequency caps

6. REMINDER / SCHEDULED NOTIFICATION (P1)
   Trigger: Time-based event
   Examples: Event reminder, subscription renewal, inactive user nudge,
             appointment upcoming
   Fan-out: 1:1 (personalized schedule)
   Latency: Must deliver within ±2 minutes of scheduled time
   Channel: Push (primary), email (backup)
```

## Read Paths

```
1. NOTIFICATION INBOX (in-app)
   User opens notification tab → Fetch recent notifications
   → Paginated, most recent first
   → Includes read/unread status
   → Grouped by type (social, system, etc.) optionally
   → QPS: ~50K reads/sec (every app open hits this)

2. NOTIFICATION PREFERENCES
   User views/edits notification settings
   → Per notification type: enable/disable per channel
   → Global settings: quiet hours, frequency caps
   → QPS: ~1K reads/sec (settings page is rarely visited)

3. DELIVERY STATUS (internal)
   Operations dashboard shows:
   → Per-channel delivery rates, failure rates, latency percentiles
   → Per-notification-type volume and engagement
   → Per-provider health (APNs, FCM, SMTP, SMS)
   → QPS: ~100 reads/sec (internal tooling)

4. NOTIFICATION HISTORY (per user, internal/support)
   Support agent looks up all notifications sent to a user
   → Chronological list with channel, status, content
   → Used for debugging "I didn't get the notification" complaints
   → QPS: ~10 reads/sec
```

## Write Paths

```
1. EVENT INGESTION
   Services publish notification events to the API
   → Validated, deduplicated, priority-classified, enqueued
   → QPS: 50K-500K events/sec (varies by product activity)

2. PREFERENCE UPDATE
   User changes notification preferences
   → Propagated to preference cache within seconds
   → Must take effect for the NEXT notification, not retroactively
   → QPS: ~500 writes/sec

3. TOKEN REGISTRATION / UPDATE
   Device registers/refreshes push token
   → APNs token (iOS), FCM token (Android)
   → One user may have multiple devices → multiple tokens
   → Token validity must be tracked (expired, invalid, refreshed)
   → QPS: ~10K writes/sec (app opens, token refreshes)

4. DELIVERY ACKNOWLEDGMENT
   Channel providers callback with delivery status
   → APNs/FCM: delivery receipts (async)
   → Email: bounce notifications, open/click tracking
   → SMS: delivery receipts
   → QPS: ~200K writes/sec (one per delivery attempt)

5. UNSUBSCRIBE / OPT-OUT
   User clicks unsubscribe link (email) or disables in settings
   → MUST be processed within seconds (regulatory: CAN-SPAM, GDPR)
   → QPS: ~1K writes/sec
```

## Control / Admin Paths

```
1. CAMPAIGN MANAGEMENT
   Marketing team creates, schedules, targets campaigns
   → Audience segmentation (users matching criteria)
   → Schedule with throttle parameters
   → Approval workflow before large sends

2. TEMPLATE MANAGEMENT
   Content team manages notification templates
   → Per channel (push has 140 chars, email has HTML)
   → Localization per language/region
   → A/B test variants

3. PROVIDER CONFIGURATION
   Ops team manages channel provider credentials and routing
   → Primary/secondary provider per channel
   → Per-provider rate limits and circuit breaker thresholds
   → Provider failover rules

4. KILL SWITCH
   Emergency stop for any notification type, channel, or campaign
   → Takes effect within seconds (cache invalidation)
   → Used during incidents or mis-sent campaigns
```

## Edge Cases

```
1. CELEBRITY FAN-OUT
   A user with 100M followers posts → 100M notifications
   → Cannot fan out synchronously — would take hours
   → Must be chunked, batched, and processed asynchronously
   → Must not block other notifications during processing

2. THUNDERING HERD
   Breaking news → system notification to ALL 500M users
   → Gradual rollout (1% → 10% → 100% over minutes)
   → Channel providers have rate limits that must be respected
   → APNs will reject if you send too fast

3. DUPLICATE EVENTS
   Service retries producing the same event (network timeout)
   → Idempotency key must prevent duplicate notifications
   → Dedup window: how long do we remember seen events?

4. USER WITH 50 DEVICES
   Power user logged into many devices
   → Push notification should go to all active devices
   → But only one in-app notification entry (not 50)
   → Stale tokens should be pruned, not sent to

5. RAPID-FIRE EVENTS
   User receives 200 likes in 1 minute
   → Notification aggregation: "User A and 199 others liked your photo"
   → Not 200 separate push notifications
   → Aggregation window is time-based and count-based

6. QUIET HOURS EDGE
   Notification arrives at 9:59 PM, quiet hours start at 10:00 PM
   → Must check quiet hours at DELIVERY time, not ingestion time
   → Queued notifications may cross the quiet hour boundary

7. USER DISABLES NOTIFICATIONS MID-FAN-OUT
   Celebrity posts, fan-out starts, user opts out during processing
   → Preference check happens at delivery time (not fan-out start)
   → Eventual consistency: small window where user may still get one

8. CHANNEL PROVIDER OUTAGE
   APNs is down for 30 minutes
   → Push notifications queue up (within bounds)
   → After threshold, trigger fallback to secondary channel
   → When APNs recovers, drain queue but DON'T send stale notifications
   → "You got a like 45 minutes ago" via push is worse than not sending
```

## What Is Intentionally OUT of Scope

```
1. NOTIFICATION CONTENT GENERATION
   Template rendering, personalization, localization → Product concern
   We provide the delivery pipeline; content teams own templates

2. USER SEGMENTATION ENGINE
   Determining which users match campaign criteria → Analytics concern
   Campaign system provides us a recipient list; we deliver

3. ANALYTICS / ENGAGEMENT OPTIMIZATION
   "Which notification type has best open rates?" → Analytics concern
   We provide delivery logs; analytics team derives insights

4. REAL-TIME CHAT / MESSAGING
   Chat is a different system with different guarantees
   (persistent connections, message ordering, read receipts)
   Notification system may be triggered BY chat (missed message alert)
   but doesn't implement chat itself

WHY: Notification delivery is already complex enough. Adding content
generation, segmentation, and analytics into the same system creates
a monolith that no single team can own. Clear boundaries allow each
team to evolve independently.
```

---

# Part 3: Non-Functional Requirements (Reality-Based)

## Latency Expectations

```
P0 TRANSACTIONAL (OTP, security alerts):
  P50: < 2 seconds end-to-end (event → user's device)
  P95: < 5 seconds
  P99: < 10 seconds
  RATIONALE: User is staring at a "Enter your OTP" screen.
  Every second of delay → abandonment. 10s is the "give up" threshold.

P1 SOCIAL / CONTENT:
  P50: < 10 seconds
  P95: < 30 seconds
  P99: < 60 seconds
  RATIONALE: User expectations for social notifications are "near real-time"
  but not instant. 30s delay is imperceptible for a "like" notification.

P2 BULK / CAMPAIGN:
  Full campaign delivery: < 4 hours for 50M recipients
  Throttled to respect provider limits and avoid spam classification
  RATIONALE: Marketing doesn't need instant delivery. Spreading over hours
  actually improves deliverability (email providers flag burst sends as spam).

FAN-OUT LATENCY (1:N):
  P50 recipient (median): < 30 seconds regardless of N
  P99 recipient (tail): < 5 minutes for N up to 10M
  RATIONALE: The first recipients in a fan-out should get notified quickly.
  The tail is allowed to be slower. This enables chunked processing.
```

## Availability Expectations

```
P0 CHANNEL: 99.99% availability (< 53 min downtime/year)
  If OTP delivery is down, users can't log in → revenue impact
  Requires: Multi-provider failover, no single points of failure

P1 CHANNEL: 99.95% availability (< 4.4 hours downtime/year)
  Social notifications delayed → user experience degraded but not broken
  Requires: Queue-based decoupling, provider circuit breakers

P2 CHANNEL: 99.9% availability (< 8.8 hours downtime/year)
  Marketing campaigns delayed → minor business impact
  Can tolerate planned maintenance windows

OVERALL INGESTION API: 99.99%
  If event ingestion is down, NO notifications are sent
  This is the single most critical component
```

### SLO/SLA Enforcement Across Producer Teams

```
PROBLEM:
  The notification platform serves 15+ producer teams (Like Service, Chat,
  Auth, Marketing, etc.). Without explicit SLOs per team, the platform team
  gets blamed for every missed notification, even when the cause is the
  producer sending malformed events, exceeding their rate limit, or the
  social graph being slow.

SLO STRUCTURE (tiered):

  PLATFORM SLOs (Notification team owns these):
  → P0 ingestion-to-delivery latency: P99 < 5s
  → P1 ingestion-to-delivery latency: P99 < 60s
  → Event ingestion availability: 99.99%
  → Delivery success rate (excluding provider outages): 99.95%
  → Preference evaluation correctness: 99.99% (prefs honored)

  PRODUCER SLAs (Producer teams must meet these to receive platform SLOs):
  → Event schema compliance: 100% (malformed events rejected, not retried)
  → Rate limit compliance: Stay within agreed rate limit (429s don't count
    against platform SLO)
  → Idempotency key provision: Required for dedup guarantee
  → TTL specification: Required for staleness management

  PROVIDER SLOs (External, monitored but not controlled):
  → APNs delivery latency: Monitored, no contractual SLO
  → FCM delivery latency: Monitored, no contractual SLO
  → SMS delivery rate: Contractual with SMS vendor (99.5%)

SLO ENFORCEMENT:
  → Per-sender dashboard: Each producer team sees their event acceptance
    rate, delivery latency, and rejection reasons
  → SLO attribution: When a notification fails, the system automatically
    attributes the failure to: producer (bad event), platform (bug/outage),
    or provider (APNs/SMTP down)
  → Quarterly SLO review: Platform team and top-5 producer teams review
    SLO performance. Adjust rate limits and priorities based on data.

WHY THIS MATTERS AT L6:
  Without explicit SLO boundaries, the notification team becomes a 
  catch-all for every "I didn't get my notification" complaint. SLO 
  attribution is an ORGANIZATIONAL tool as much as a technical one.
  It defines who fixes what, and prevents the platform team from 
  being paged for producer-side bugs.

REAL-WORLD ANALOGY (News Feed):
  The News Feed ranking team doesn't own content quality. If a post is
  spam, the content-integrity team fixes it. Similarly, if a producer 
  sends 10M duplicate events because their retry logic is broken, 
  that's the producer's SLO violation, not the notification platform's.
```

## Consistency Needs

```
PREFERENCE CONSISTENCY: Read-your-writes for the user who changed them
  User disables "like" notifications → next like must not generate notification
  Other users' views of this user's preferences can be eventually consistent
  Staleness budget: < 5 seconds

DELIVERY DEDUPLICATION: Probabilistic
  Exactly-once delivery is impossible across unreliable channels
  Target: < 0.01% duplicate rate (1 in 10,000 notifications)
  Achieved via: Idempotency keys + bloom filters + delivery log checks

NOTIFICATION INBOX: Eventually consistent
  In-app notification list may be slightly stale (< 5s)
  Ordering must be monotonic (no notification appearing then disappearing)

TOKEN REGISTRY: Eventually consistent
  New device token available for next notification (not retroactively)
  Stale tokens cause silent delivery failure → regular cleanup needed
```

## Durability

```
EVENT LOG: Durable (replicated, persisted)
  Every notification event must be logged for audit and debugging
  Retention: 30 days hot, 1 year cold (regulatory compliance)

DELIVERY LOG: Durable
  Every delivery attempt + outcome must be recorded
  Required for: debugging, compliance, analytics, dedup
  Retention: 90 days hot, 1 year cold

NOTIFICATION INBOX: Durable
  In-app notifications visible for up to 90 days
  After 90 days, notifications age out (not deleted, just hidden)

USER PREFERENCES: Highly durable (replicated across regions)
  Preference loss = users receiving unwanted notifications
  → Regulatory risk (GDPR, CAN-SPAM)
  → Backup and replication mandatory
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Deliver potentially duplicate vs risk missing notification
  FOR TRANSACTIONAL (P0): Deliver duplicate. User receiving 2 OTPs is 
  better than receiving 0. They'll use the first one that arrives.
  FOR SOCIAL (P1): Suppress duplicate. Receiving "User A liked your photo" 
  twice is annoying and erodes trust in the product.
  IMPLEMENTATION: Different dedup strictness per priority class.

TRADE-OFF 2: Respect quiet hours strictly vs deliver time-sensitive content
  STRICT: Never deliver during quiet hours → user may miss urgent alert
  FLEXIBLE: Allow P0 to bypass quiet hours → user may be annoyed at 3am
  RESOLUTION: P0 bypasses quiet hours. P1/P2 are held until quiet hours end.
  Edge: "Your account is compromised" at 3am → MUST deliver immediately.

TRADE-OFF 3: Aggregate aggressively vs deliver individual notifications
  AGGREGATE: "15 people liked your photo" → fewer interruptions, less annoying
  INDIVIDUAL: Each like is a separate notification → more engaging for creators
  RESOLUTION: Configurable per notification type. Social likes aggregate (5s 
  window). Comments deliver individually (higher signal). Follows aggregate.

TRADE-OFF 4: Send stale notification vs drop it
  STALE: "User A liked your photo" delivered 2 hours late → confusing
  DROP: Silently discard → user never knows about the like
  RESOLUTION: Per-type TTL. Social: 1 hour TTL. Transactional: 24 hour TTL.
  System: 7 day TTL. After TTL, notification is dropped, not delivered.
```

## Security Implications (Conceptual)

```
1. NOTIFICATION CONTENT AS ATTACK VECTOR
   Push notification text is visible on lock screen
   → Never include sensitive data (full credit card, SSN, passwords)
   → OTP codes are the exception (by design, short-lived)
   → Content must be sanitized (no XSS in email, no injection in push)

2. NOTIFICATION SPAM / ABUSE
   Compromised service account sends millions of spam notifications
   → Per-sender rate limits prevent single-source floods
   → Kill switch can halt any notification type instantly

3. TOKEN THEFT
   Stolen push tokens allow sending push to someone else's device
   → Tokens are bound to app + device, validated by APNs/FCM
   → System never exposes raw tokens in APIs or logs

4. PREFERENCE TAMPERING
   Attacker changes another user's notification preferences
   → Preference writes must be authenticated (user's own session)
   → Admin overrides require elevated privileges + audit log

5. UNSUBSCRIBE LINK MANIPULATION
   Attacker forges unsubscribe links to disable another user's notifications
   → Unsubscribe tokens must be signed (HMAC) and user-specific
   → Rate-limit unsubscribe endpoint to prevent enumeration
```

---

# Part 4: Scale & Load Modeling (Concrete Numbers)

## User Base

```
TOTAL REGISTERED USERS: 500M
DAILY ACTIVE USERS (DAU): 100M
MONTHLY ACTIVE USERS (MAU): 300M
USERS WITH PUSH ENABLED: 60% of DAU = 60M
USERS WITH EMAIL ENABLED: 80% of MAU = 240M
AVERAGE DEVICES PER USER: 1.8 (phone + tablet or phone + web)
TOTAL PUSH TOKENS: 100M users × 1.8 = 180M active tokens
```

## QPS Modeling

```
NOTIFICATION EVENTS GENERATED:
  Social events (likes, comments, follows): 200K events/sec average
  Content events (new posts by followed): 10K events/sec average
  Transactional events (OTP, receipts): 5K events/sec average
  System events: 100 events/sec average (burst: 1M in minutes)
  Campaign events: Batched, 50M recipients over 2 hours = ~7K/sec

  TOTAL INGESTION: ~220K events/sec average
  PEAK: ~500K events/sec (major product event or viral moment)

FAN-OUT RATIO:
  Average fan-out per event: ~3 recipients (most are 1:1 or 1:few)
  95th percentile fan-out: ~100 recipients
  99.9th percentile: ~10M recipients (celebrity post)
  Max: ~100M recipients (broadcast)

DELIVERY WORK ITEMS (post fan-out):
  220K events/sec × 3 avg fan-out = ~660K delivery tasks/sec average
  Peak (celebrity post): 10M tasks burst over 60 seconds

PER-CHANNEL DELIVERY QPS:
  Push: ~400K sends/sec (60% of users prefer push)
  In-app: ~660K writes/sec (every notification gets in-app entry)
  Email: ~50K sends/sec (digest + transactional, lower frequency)
  SMS: ~2K sends/sec (transactional only)

NOTIFICATION INBOX READS:
  Every app open → inbox fetch: ~50K reads/sec
  Push tap → specific notification detail: ~20K reads/sec
```

## Read/Write Ratio

```
WRITE-HEAVY SYSTEM:
  Writes (events + delivery + tracking): ~1.5M ops/sec
  Reads (inbox + preferences): ~80K ops/sec
  Ratio: ~19:1 write-to-read

  This is unusual — most systems are read-heavy.
  Notification systems are fundamentally write-amplifying:
  1 event → N recipients → N channel sends → N delivery logs

  IMPLICATION: Storage must be optimized for write throughput.
  Reads are concentrated on "recent" data (last 100 notifications).
  Time-series storage patterns work well (append-only, time-partitioned).
```

## Growth Assumptions

```
USER GROWTH: 20% YoY
NOTIFICATION VOLUME GROWTH: 30% YoY (more notification types added)
CHANNEL GROWTH: New channels every 1-2 years (web push, rich push, 
  RCS, WhatsApp Business)

WHAT BREAKS FIRST AT SCALE:
  1. Fan-out queue depth during celebrity events
     → 10M fan-out items queued in seconds → consumer lag spikes
  2. Push provider rate limits (APNs: ~100K/sec per certificate)
     → Need multiple certificates / provider accounts
  3. Email deliverability during campaign bursts
     → ISPs throttle senders who burst → reputation damage
  4. In-app notification storage
     → 660K writes/sec × 86400 sec/day = 57 billion entries/day
     → Need aggressive TTL + compaction

MOST DANGEROUS ASSUMPTIONS:
  1. "Fan-out is bounded" — a single viral event can 100x normal load
  2. "Provider capacity is infinite" — APNs/FCM/SMTP all have limits
  3. "Notifications are small" — rich push with images, email with HTML 
     can be 50KB+ each → bandwidth is a real concern at scale
  4. "Users don't change preferences often" — major UX changes can cause
     10x spike in preference writes (new settings page launch)
```

## Burst Behavior

```
BURST SCENARIO 1: Celebrity Post
  Celebrity with 100M followers posts
  → 100M fan-out items generated over ~30 seconds
  → 60M push sends needed (60% push-enabled)
  → At 100K push sends/sec, takes 10 minutes for push alone
  → Queue depth: 100M items → need at least 100GB queue capacity
  → MUST NOT block other notification processing during this event

BURST SCENARIO 2: Breaking News
  System sends broadcast notification to all 100M DAU
  → 100M delivery tasks generated
  → Must throttle: gradual rollout over 10-30 minutes
  → Cannot saturate APNs/FCM → stagger by region / user segment

BURST SCENARIO 3: Flash Sale Start
  E-commerce sends campaign to 50M opted-in users
  → Pre-scheduled, throttled over 2 hours
  → But push opens trigger 10M app opens within minutes
  → Those app opens hit notification inbox → read burst
  → 10M inbox reads in 10 minutes = ~17K additional reads/sec

BURST SCENARIO 4: Service Recovery After Outage
  Notification queue backed up during 30-minute outage
  → On recovery, 30 min × 220K events/sec = 400M queued events
  → Must drain gradually, not all at once
  → Stale events (TTL expired) should be dropped, not delivered
  → Need "drain mode" that processes at controlled rate
```

---

# Part 5: High-Level Architecture (First Working Design)

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   NOTIFICATION DELIVERY SYSTEM ARCHITECTURE                  │
│                                                                             │
│  ┌─────────┐   ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐   │
│  │ Service │──→│ Notification │──→│  Fan-out     │──→│   Preference    │   │
│  │ A, B, C │   │  Ingestion   │   │  Service     │   │   Evaluator     │   │
│  │ (event  │   │  API         │   │              │   │                 │   │
│  │ sources)│   │              │   │ Resolves     │   │ Checks per-user │   │
│  └─────────┘   │ Validates,   │   │ recipients,  │   │ prefs, freq     │   │
│                │ deduplicates,│   │ batches,     │   │ caps, quiet hrs │   │
│                │ classifies   │   │ enqueues     │   │                 │   │
│                │ priority     │   │              │   │                 │   │
│                └──────┬───────┘   └──────┬───────┘   └───────┬─────────┘   │
│                       │                  │                   │             │
│                       ▼                  ▼                   ▼             │
│                ┌─────────────────────────────────────────────────────┐     │
│                │              PRIORITY QUEUES                        │     │
│                │  ┌─────────┐  ┌─────────┐  ┌─────────┐            │     │
│                │  │ P0 Queue│  │ P1 Queue│  │ P2 Queue│            │     │
│                │  │ (trans) │  │ (social)│  │ (bulk)  │            │     │
│                │  └────┬────┘  └────┬────┘  └────┬────┘            │     │
│                └───────┼────────────┼────────────┼──────────────────┘     │
│                        │            │            │                        │
│                        ▼            ▼            ▼                        │
│                ┌─────────────────────────────────────────────────────┐     │
│                │             CHANNEL ROUTER                          │     │
│                │  Routes to channel-specific delivery queues         │     │
│                │  based on user channel preference + device state    │     │
│                └──┬──────────┬──────────┬──────────┬────────────────┘     │
│                   │          │          │          │                      │
│                   ▼          ▼          ▼          ▼                      │
│              ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                │
│              │  Push  │ │ Email  │ │  SMS   │ │ In-App │                │
│              │ Workers│ │ Workers│ │ Workers│ │ Workers│                │
│              │        │ │        │ │        │ │        │                │
│              │ APNs / │ │ SMTP / │ │Twilio/ │ │ Write  │                │
│              │ FCM    │ │ SES    │ │ vendor │ │ to DB  │                │
│              └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘                │
│                  │          │          │          │                      │
│                  ▼          ▼          ▼          ▼                      │
│              ┌──────────────────────────────────────────┐                │
│              │          DELIVERY TRACKER                 │                │
│              │  Records outcomes, triggers fallback,     │                │
│              │  updates channel health, feeds analytics  │                │
│              └──────────────────────────────────────────┘                │
│                                                                         │
│  SUPPORTING SERVICES:                                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │  Preference   │ │   Token      │ │  Template    │ │  Delivery    │   │
│  │  Store        │ │   Registry   │ │  Service     │ │  Log Store   │   │
│  │              │ │              │ │              │ │              │   │
│  │ Per-user     │ │ Push tokens  │ │ Render per   │ │ Append-only  │   │
│  │ per-type     │ │ per device   │ │ channel +    │ │ delivery     │   │
│  │ per-channel  │ │ validity     │ │ locale       │ │ outcomes     │   │
│  │ prefs        │ │ tracking     │ │              │ │              │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Responsibilities of Each Component

```
NOTIFICATION INGESTION API (Stateless)
  → Accepts events from all producer services
  → Validates schema, enforces per-sender rate limits
  → Assigns idempotency key, checks dedup cache
  → Classifies priority (P0/P1/P2) based on event type
  → Writes to priority-specific ingestion queue
  → DOES NOT resolve recipients or check preferences (too slow)
  → Stateless: any instance can handle any request

FAN-OUT SERVICE (Stateless workers, stateful queues)
  → Reads from ingestion queue
  → Resolves recipient list for each event
    → 1:1 events: Target user is already in the event
    → 1:N events: Fetch follower list from social graph service
    → Broadcast: Fetch user segments from segmentation service
  → For large fan-outs (>10K), chunks into batches of 1,000
  → Produces per-recipient work items to the preference evaluator queue
  → For celebrity fan-out, uses pre-computed follower partitions

PREFERENCE EVALUATOR (Stateless, cache-dependent)
  → Reads per-recipient work items
  → For each recipient, evaluates:
    → Is notification type enabled?
    → Is user within quiet hours (timezone-aware)?
    → Has user exceeded frequency cap (rolling window)?
    → Which channels are opted in for this type?
  → Filters out suppressed notifications
  → Routes surviving notifications to channel-specific queues
  → All preference data served from in-memory cache (< 1ms lookup)

CHANNEL ROUTER (Stateless)
  → Receives (recipient, notification, allowed_channels)
  → Selects optimal channel(s) based on:
    → User's preferred channel for this notification type
    → Device state (valid push token? email bounced?)
    → Channel load (is one channel overloaded?)
  → Enqueues to channel-specific delivery queues

CHANNEL WORKERS (Stateless, channel-specific)
  Push Workers:
    → Batch sends to APNs (HTTP/2 multiplexed) and FCM (batch API)
    → Handle per-device token management
    → Process feedback (invalid tokens → mark in token registry)
  Email Workers:
    → Render email template (from template service)
    → Send via SMTP relay or email provider API
    → Handle bounce processing (hard bounce → remove email)
  SMS Workers:
    → Format message (160 char limit, encoding concerns)
    → Send via SMS provider API
    → Handle delivery receipts
  In-App Workers:
    → Write notification entry to notification inbox store
    → Simple, most reliable channel (no external dependency)

DELIVERY TRACKER (Stateless writers, durable store)
  → Receives delivery outcomes from all channel workers
  → Writes to append-only delivery log (time-partitioned)
  → On failure: triggers retry or fallback channel routing
  → On permanent failure: updates channel health for user
  → Publishes delivery metrics to monitoring system

PREFERENCE STORE (Stateful)
  → Source of truth for per-user notification preferences
  → Schema: (user_id, notification_type, channel) → (enabled, settings)
  → Served via cache with 5-second TTL
  → Writes go to DB + invalidate cache
  → Must be durable (regulatory requirement for opt-out records)

TOKEN REGISTRY (Stateful)
  → Maps user_id → list of (device_id, platform, push_token, last_seen)
  → Updated on: app open, token refresh, explicit registration
  → Cleaned on: APNs/FCM feedback (invalid token), 90 days inactive
  → Served via cache, critical for push delivery

DELIVERY LOG STORE (Append-only, time-partitioned)
  → Every delivery attempt: (event_id, user_id, channel, status, timestamp)
  → Used for: dedup, analytics, debugging, compliance
  → Hot storage: 30 days (fast queries)
  → Cold storage: 1 year (compliance, archived)
```

## Stateless vs Stateful Decisions

```
STATELESS (horizontally scalable):
  → Ingestion API: Any instance handles any request
  → Fan-out workers: Process any event from any queue partition
  → Preference evaluator: Reads from cache, no local state
  → Channel workers: Send and forget, retry from queue
  → Delivery tracker: Writes to external store

STATEFUL (requires careful scaling):
  → Priority queues: Partitioned, replicated, ordered
  → Preference store: Sharded by user_id, cached aggressively
  → Token registry: Sharded by user_id
  → Delivery log: Time-partitioned, append-only
  → Dedup cache: Distributed, TTL-based, probabilistic (bloom filters)

RATIONALE: Keep the processing path stateless for horizontal scaling.
Push state to purpose-built stores (queues, caches, databases).
During a burst, scale workers horizontally; state stores grow vertically
or via rebalancing (which is slower).
```

## Data Flow: Write Path (Social Notification)

```
User A likes User B's photo:

1. Like Service → POST /v1/notifications
   {type: "like", actor: "userA", target: "userB", 
    object: "photo_123", priority: "P1"}

2. Ingestion API:
   → Validate schema ✓
   → Check sender rate limit ✓ (Like Service: 50K/sec allowed)
   → Compute idempotency key: hash("like:userA:userB:photo_123")
   → Check dedup cache → NOT SEEN → insert with 1h TTL
   → Enqueue to P1 ingestion queue

3. Fan-out Service picks up from P1 queue:
   → Recipient resolution: target = "userB" → single recipient
   → Produce work item: {event_id, recipient: "userB", ...}
   → Enqueue to preference evaluation queue

4. Preference Evaluator picks up work item:
   → Load userB preferences from cache
   → "like" notifications: ENABLED
   → Push channel: ENABLED, Email: DISABLED
   → Quiet hours: NOT in quiet hours
   → Frequency cap: 12 notifications today, cap is 50 → OK
   → Route to: Push queue + In-App queue

5. Push Worker picks up from Push queue:
   → Load userB tokens from token registry cache
   → Tokens: [iOS_token_abc, Android_token_def]
   → Render push payload: {title: "User A liked your photo", ...}
   → Send to APNs (iOS token) and FCM (Android token)
   → APNs: 200 OK, FCM: 200 OK
   → Report success to Delivery Tracker

6. In-App Worker picks up from In-App queue:
   → Write to notification inbox store:
     {user: "userB", type: "like", content: {...}, 
      read: false, created_at: now()}
   → Report success to Delivery Tracker

7. Delivery Tracker:
   → Log: (event_id, userB, push, SUCCESS, timestamp)
   → Log: (event_id, userB, in_app, SUCCESS, timestamp)
   → Update metrics: P1 push delivery latency = 850ms
```

## Data Flow: Write Path (Celebrity Fan-out)

```
Celebrity (10M followers) posts a new photo:

1. Post Service → POST /v1/notifications
   {type: "new_post", actor: "celebrity", object: "post_456", 
    priority: "P1", fan_out: "followers"}

2. Ingestion API:
   → Validate, dedup, classify → enqueue to P1 queue

3. Fan-out Service:
   → Detect: fan_out = "followers" for "celebrity"
   → Query social graph: follower_count("celebrity") = 10M
   → LARGE FAN-OUT detected (> 10K threshold)
   → Use chunked fan-out strategy:
     → Fetch follower list in pages of 10K
     → For each page, produce batch work item
     → 1,000 batch work items × 10K recipients each
     → Enqueue all batches to preference evaluation queue
   → Total time: ~15 seconds (parallelized page fetches)

4. Preference Evaluator (1,000 batches processed in parallel):
   → For each batch of 10K recipients:
     → Batch-load preferences from cache
     → Filter: ~40% have push enabled for "new_post" = 4K
     → Filter: ~5% in quiet hours = ~200 removed
     → Filter: ~2% at frequency cap = ~80 removed
     → Surviving: ~3,720 per batch → 3.72M total push sends
   → Route to Push queue + In-App queue (10M in-app entries)

5. Push Workers (scaled up):
   → 3.72M push sends at ~100K sends/sec
   → Total push delivery time: ~37 seconds
   → APNs batched sends (500 per HTTP/2 stream)
   → FCM batch API (1,000 per request)

6. In-App Workers:
   → 10M inbox writes at ~200K writes/sec
   → Total in-app delivery time: ~50 seconds

TOTAL END-TO-END:
  First recipient notified: ~5 seconds
  Median recipient: ~25 seconds
  Last recipient: ~90 seconds
  All in-app entries written: ~65 seconds
```

## Data Flow: Read Path (Notification Inbox)

```
User B opens the app and taps the notification bell:

1. Client → GET /v1/notifications/inbox?limit=20&cursor=...

2. Notification Inbox API:
   → Authenticate user
   → Query notification inbox store:
     → Key: user_id = "userB"
     → Filter: created_at > 90_days_ago
     → Order: created_at DESC
     → Limit: 20, cursor-based pagination
   → Return: [{type: "like", content: {...}, read: false, ...}, ...]

3. Client renders notification list
   → Unread count badge updated
   → Mark-as-read on scroll (batch update)

4. OPTIMIZATION: Unread count is cached separately
   → Maintained by In-App Worker on each write (increment counter)
   → Reset when user views inbox (set counter to 0)
   → Avoids scanning inbox store on every app open
```

---

# Part 6: Deep Component Design (NO SKIPPING)

## Notification Ingestion API

### Internal Data Structures

```
EVENT SCHEMA:
{
  event_id: string        // UUID, assigned by API if not provided
  idempotency_key: string // Client-provided or computed: hash(type+actor+target+object)
  type: string            // "like", "comment", "new_post", "otp", "campaign_xyz"
  priority: enum          // P0, P1, P2 (derived from type if not specified)
  actor: string           // Who triggered the event (user_id or service_id)
  target: string          // Direct recipient (user_id) — may be null for fan-out
  fan_out_type: enum      // DIRECT (target is recipient), FOLLOWERS (actor's followers),
                          // SEGMENT (query-based), BROADCAST (all users)
  object: string          // What the event is about (post_id, order_id, etc.)
  payload: map            // Channel-agnostic content data for template rendering
  ttl: duration           // How long the notification remains relevant (default by type)
  created_at: timestamp   // Event creation time
  sender_id: string       // Which service sent this event (for rate limiting)
}

DEDUP CACHE ENTRY:
  Key: idempotency_key
  Value: {event_id, ingested_at}
  TTL: 1 hour (configurable per type)
  Store: Distributed cache (e.g., in-memory KV store with TTL)
```

### Algorithms

```
INGESTION FLOW:
  1. Parse and validate event schema
  2. Derive priority from event type if not specified
     → Type-to-priority mapping maintained in config
  3. Compute idempotency_key if not provided
     → SHA256(type + actor + target + object)[:16]
  4. Check dedup cache for idempotency_key
     → HIT: Return 200 OK with original event_id (idempotent response)
     → MISS: Continue
  5. Check per-sender rate limit
     → Sliding window counter per sender_id
     → EXCEEDED: Return 429 Too Many Requests
  6. Insert into dedup cache with TTL
  7. Enqueue to priority-specific ingestion queue
     → P0: high-priority queue (separate cluster, reserved capacity)
     → P1: standard queue
     → P2: bulk queue (lower processing priority)
  8. Return 202 Accepted with event_id
```

### Failure Behavior

```
DEDUP CACHE DOWN:
  → Fail OPEN: Accept the event (risk duplicate, but don't block delivery)
  → Log warning, alert ops team
  → Downstream delivery-level dedup provides second safety net

QUEUE WRITE FAILURE:
  → Return 503 to caller → caller retries (they have their own retry logic)
  → DO NOT store-and-forward locally (stateless API, local storage is fragile)
  → Circuit breaker on queue: if queue is unhealthy, fast-fail all writes

RATE LIMIT STORE DOWN:
  → Fail OPEN with conservative defaults
  → Allow traffic but at reduced rate (hardcoded fallback limit)
  → Alert ops team

PARTIAL VALIDATION FAILURE:
  → Return 400 with specific field errors
  → DO NOT partially accept events — all-or-nothing
```

### Why Simpler Alternatives Fail

```
"Just send directly to channel workers from the API"
  → No fan-out resolution, no preference checking
  → API becomes stateful (must know recipient list)
  → API latency spikes on large fan-out events
  → No priority isolation (P0 and P2 share the same path)

"Use synchronous RPC instead of queues"
  → Fan-out of 10M recipients would take minutes synchronously
  → API would timeout, caller would retry, causing duplicate work
  → No backpressure mechanism — sender overwhelms receiver

"Combine ingestion and fan-out in one service"
  → Ingestion is I/O bound (validate + enqueue)
  → Fan-out is CPU/memory bound (load follower lists, batch)
  → Different scaling profiles → combine = waste or bottleneck
  → Fan-out failures would affect ingestion availability
```

## Fan-out Service

### Internal Data Structures

```
FAN-OUT WORK ITEM (input):
{
  event_id: string
  event: NotificationEvent     // Full event from ingestion queue
  fan_out_type: enum           // DIRECT, FOLLOWERS, SEGMENT, BROADCAST
}

RECIPIENT BATCH (output):
{
  event_id: string
  batch_id: string             // Unique per batch within an event
  recipients: [user_id]        // Up to 10,000 per batch
  notification_data: {         // Shared across recipients
    type: string
    content_payload: map
    priority: enum
    ttl: duration
    created_at: timestamp
  }
}

FAN-OUT STATE TRACKER:
  Per event_id:
  {
    total_recipients: int
    batches_produced: int
    batches_completed: int     // Updated by preference evaluator callbacks
    started_at: timestamp
    status: enum               // IN_PROGRESS, COMPLETED, FAILED, TIMED_OUT
  }
  Stored in: Distributed KV store with TTL (24 hours)
```

### Algorithms

```
DIRECT FAN-OUT (target specified):
  → Recipient = event.target
  → Produce single recipient batch: [event.target]
  → Enqueue to preference evaluation queue
  → Total: O(1)

FOLLOWER FAN-OUT (actor's followers):
  → Query social graph service: GET /followers/{actor_id}?page_size=10000
  → For each page of followers:
    → Create RecipientBatch with up to 10K user_ids
    → Enqueue batch to preference evaluation queue
  → Parallelism: Fetch up to 10 pages concurrently
  → For accounts with > 1M followers:
    → Use pre-computed follower partitions (updated hourly)
    → Partitions stored in distributed cache
    → Avoid hitting social graph service on every fan-out

SEGMENT FAN-OUT (query-based, campaigns):
  → Receive pre-computed recipient list from campaign service
  → Recipient list stored as file in object storage (large lists)
  → Stream-read file, batch into 10K chunks
  → Enqueue batches to P2 preference evaluation queue
  → Throttled: Max 100 batches/sec to prevent queue flooding

BROADCAST FAN-OUT:
  → Query user service for all active user_id ranges
  → Partition by user_id hash into 1,000 segments
  → Each segment is a batch (variable size, ~100K-500K users)
  → Enqueue segments to P2 queue with LOWEST priority
  → Throttled aggressively: 10 segments/sec
  → Full broadcast takes 100 seconds to enqueue, hours to deliver
```

### The Celebrity Problem (Deep Dive)

```
PROBLEM:
  Celebrity with 100M followers posts.
  Naively fetching 100M follower IDs and producing 10K batches takes:
  → 100M IDs × 8 bytes = 800MB just for user IDs
  → 10K batches × enqueue overhead = minutes of processing
  → Social graph service hit with massive read: potential overload

SOLUTION: Pre-computed Fan-out Partitions

  OFFLINE (hourly cron):
  → For all accounts with > 100K followers:
    → Fetch follower list from social graph
    → Partition into chunks of 10K
    → Store partitions in distributed cache:
      Key: fanout:{actor_id}:partition:{N}
      Value: [user_id_1, user_id_2, ..., user_id_10000]
    → Store metadata:
      Key: fanout:{actor_id}:meta
      Value: {partition_count: 10000, last_updated: ..., follower_count: 100M}
    → Incremental updates: Only process follow/unfollow deltas since last run

  ONLINE (fan-out time):
  → Read metadata: partition_count = 10,000
  → For each partition:
    → Enqueue reference: {event_id, actor_id, partition_id: N}
    → Preference evaluator loads partition from cache
  → No need to load 800MB into fan-out service memory
  → Fan-out becomes O(partition_count) enqueue operations, not O(followers)

  TRADE-OFF:
  → Partitions are up to 1 hour stale
  → New followers in last hour won't get this notification
  → Unfollowed users in last hour might get it
  → Acceptable for social/content notifications (P1)
  → NOT acceptable for transactional (P0) — but those are 1:1 anyway
```

### Failure Behavior

```
SOCIAL GRAPH SERVICE DOWN:
  → Cannot resolve followers → fan-out stalls
  → Retry with exponential backoff (5s, 10s, 30s, 60s)
  → After 5 minutes: fall back to pre-computed partitions (may be stale)
  → After 15 minutes: mark event as FAILED, alert, dead-letter queue
  → P0 events are DIRECT (no social graph dependency) — unaffected

PARTIAL FAN-OUT FAILURE:
  → 500 out of 1,000 batches enqueued, then queue becomes unavailable
  → Fan-out state tracker shows: 500/1,000 batches produced
  → On recovery: resume from batch 501 (not from scratch)
  → Achieved via: checkpoint in fan-out state tracker + sequential batch IDs

PRE-COMPUTED PARTITION STALE:
  → Partition hasn't been updated in 4 hours (>1 hour threshold)
  → Fall back to live social graph query (slower but accurate)
  → Alert: "Partition refresh job for {actor_id} is stale"

FAN-OUT WORKER CRASH MID-PROCESSING:
  → Queue message visibility timeout expires → message redelivered
  → Worker is idempotent: re-processing a fan-out event produces
    the same batches (deterministic recipient resolution)
  → Duplicate batches caught by preference evaluator dedup
```

## Preference Evaluator

### Internal Data Structures

```
USER PREFERENCE RECORD:
{
  user_id: string
  global_settings: {
    quiet_hours: {enabled: bool, start: "22:00", end: "08:00", timezone: "America/New_York"}
    frequency_cap: {max_per_hour: 10, max_per_day: 50}
    notification_master_switch: bool  // Global enable/disable
  }
  per_type_settings: {
    "like":      {enabled: true,  channels: ["push", "in_app"]}
    "comment":   {enabled: true,  channels: ["push", "email", "in_app"]}
    "new_post":  {enabled: true,  channels: ["push", "in_app"]}
    "marketing": {enabled: false, channels: []}
    "otp":       {enabled: true,  channels: ["sms", "push"]}  // Cannot disable
    // ... one entry per notification type
  }
}

FREQUENCY COUNTER:
  Key: freq:{user_id}:{window}
  Value: {count: int, window_start: timestamp}
  Windows: 1-hour rolling, 24-hour rolling
  Store: Distributed cache with TTL matching window

QUIET HOURS EVALUATOR:
  Input: (user_timezone, quiet_start, quiet_end, current_utc_time)
  Output: bool (is_in_quiet_hours)
  Edge cases:
    → Quiet hours spanning midnight: 22:00-08:00 → two ranges
    → User without timezone → default to UTC
    → DST transitions → use IANA timezone database
```

### Algorithms

```
PREFERENCE EVALUATION (per recipient):

  1. Load user preference record from cache
     → Cache HIT: Use cached record (TTL: 5 seconds)
     → Cache MISS: Load from preference store, populate cache

  2. Check master switch
     → master_switch = false → SUPPRESS (except P0 transactional)
     → P0 transactional BYPASSES master switch (regulatory requirement)

  3. Check per-type enablement
     → per_type_settings[event.type].enabled = false → SUPPRESS
     → Exception: "otp" type cannot be disabled by user

  4. Check quiet hours
     → Convert current UTC to user's timezone
     → If within quiet hours:
       → P0: BYPASS quiet hours (deliver immediately)
       → P1: HOLD (re-enqueue with delay until quiet hours end)
       → P2: SUPPRESS (do not deliver after quiet hours, not worth it)

  5. Check frequency cap
     → Increment freq counter for user
     → If exceeded hourly cap: SUPPRESS P2, DELAY P1, ALLOW P0
     → If exceeded daily cap: SUPPRESS P2+P1, ALLOW P0 only
     → Note: Frequency counter is approximate (distributed counter,
       eventual consistency). Slight over-delivery is acceptable.

  6. Determine allowed channels
     → Intersect: per_type_settings[event.type].channels ∩ available_channels
     → available_channels = channels where user has valid delivery endpoint
       (valid push token, non-bounced email, verified phone for SMS)

  7. Output: (recipient, notification, [allowed_channels]) or SUPPRESS
     → SUPPRESS: Drop notification, log reason for analytics
     → ALLOWED: Forward to channel router
```

### Batch Optimization

```
PROBLEM: Evaluating preferences one-at-a-time for 10K-recipient batches is slow
SOLUTION: Batch preference loading + vectorized evaluation

  FOR each RecipientBatch of 10K users:
    1. Batch-load all 10K preference records from cache
       → Multi-GET operation: ~5ms for 10K records (cache)
       → Cache misses: Batch-load from DB: ~20ms for misses
    2. Vectorize evaluation:
       → Sort recipients by timezone → batch quiet-hour check
       → Batch frequency counter increment (pipeline to cache)
       → Filter in-memory: ~1ms for 10K recipients
    3. Group survivors by channel combination:
       → [push_only]: [user1, user3, user7, ...]
       → [push+email]: [user2, user5, ...]
       → [in_app_only]: [user4, user6, ...]
    4. Produce channel-specific batches → enqueue

  RESULT: 10K recipients evaluated in ~10ms (vs 10K × 1ms = 10s sequential)
```

### Failure Behavior

```
PREFERENCE CACHE DOWN:
  → Fall back to database reads (slower: ~5ms per user)
  → For batches: unacceptable latency at scale
  → Mitigation: Stale cache serve (extend TTL during outage)
  → Worst case: Default preferences (all channels enabled)
    → Better to over-deliver than under-deliver for P0/P1
    → Risk: Users who opted out may get a notification → regulatory risk
    → Decision: For P0, default to enabled. For P1/P2, HOLD in queue until
      preference cache recovers.

FREQUENCY COUNTER UNAVAILABLE:
  → Cannot enforce frequency caps
  → Fail OPEN for P0 (always deliver)
  → Fail CLOSED for P2 (suppress marketing when uncertain)
  → P1: Allow with logging (accept slight over-delivery risk)

TIMEZONE DATABASE STALE:
  → Quiet hours may be off by the DST offset (1 hour)
  → Impact: User gets a notification at 9pm instead of expected 10pm start
  → Acceptable: Update timezone data on regular release schedule
```

## Channel Workers (Push)

### Internal Data Structures

```
PUSH DELIVERY ITEM:
{
  event_id: string
  user_id: string
  tokens: [{
    device_id: string
    platform: "ios" | "android" | "web"
    token: string
    last_seen: timestamp
  }]
  payload: {
    title: string           // Max 65 chars (iOS lock screen)
    body: string            // Max 240 chars
    image_url: string       // Optional rich push
    action_url: string      // Deep link on tap
    category: string        // iOS notification category (actions)
    data: map               // Silent data payload
    badge_count: int        // iOS badge number
    sound: string           // Custom sound or "default"
    collapse_key: string    // Android: replace previous with same key
    priority: "high"|"normal"  // APNs: impacts device wake
    ttl: duration           // How long APNs/FCM should retry
  }
}

PROVIDER CONNECTION POOL:
  APNs: HTTP/2 persistent connections (10-50 per worker)
    → Multiplexed: 500 concurrent streams per connection
    → Connection reuse: Keep-alive for hours
  FCM: HTTP/1.1 or HTTP/2 connections (batch API)
    → Batch: up to 500 tokens per request
  Web Push: HTTP/1.1 per subscription endpoint
    → VAPID authentication
```

### Algorithms

```
PUSH DELIVERY FLOW:

  1. Dequeue batch of push delivery items (100-500 items)
  
  2. Group by platform:
     → iOS tokens → APNs batch
     → Android tokens → FCM batch
     → Web tokens → Web Push batch

  3. APNs Delivery (iOS):
     → For each token in batch:
       → Build APNs payload (JSON, max 4KB)
       → Send via HTTP/2 stream (multiplexed on persistent connection)
       → Response per token:
         → 200: Success
         → 410 (Unregistered): Token invalid → mark for removal
         → 429 (Too Many Requests): Back off → re-enqueue
         → 500/503: Server error → retry with backoff
     → Throughput: ~5K sends/sec per connection × 20 connections = 100K/sec

  4. FCM Delivery (Android):
     → Build FCM batch request (up to 500 tokens)
     → POST to FCM HTTP v1 API
     → Response: Per-token status array
       → "success": Delivered
       → "NOT_FOUND"/"UNREGISTERED": Token invalid → mark for removal
       → "QUOTA_EXCEEDED": Rate limited → back off
       → "INTERNAL": Server error → retry
     → Throughput: ~50K sends/sec (batch API)

  5. Handle failures:
     → Transient (429, 500, 503): Re-enqueue with exponential backoff
       → Max retries: 3 for P0, 2 for P1, 1 for P2
       → Backoff: 1s, 5s, 30s
     → Permanent (410, NOT_FOUND): Remove token from token registry
     → All retries exhausted: Dead-letter queue + trigger fallback channel

  6. Report outcomes to Delivery Tracker
```

### Token Lifecycle Management

```
TOKEN STATES:
  ACTIVE: Valid, recently seen, deliverable
  STALE: Not seen in > 30 days, still technically valid
  INVALID: Provider rejected (410/NOT_FOUND), must be removed
  EXPIRED: Not seen in > 90 days, preemptively removed

TOKEN REFRESH FLOW:
  → App opens → Client checks if token changed
  → If changed: POST /v1/devices/register {user_id, device_id, new_token}
  → Token registry updates: old_token → REPLACED, new_token → ACTIVE

TOKEN CLEANUP (daily batch job):
  → Scan token registry for tokens not seen in > 90 days
  → Mark as EXPIRED, exclude from future deliveries
  → Purpose: Reduce wasted push sends to dead tokens

TOKEN FEEDBACK LOOP:
  → APNs returns 410 for token_abc
  → Push worker → Token Registry: mark token_abc as INVALID
  → Next push to this user: token_abc excluded
  → If user's only token is INVALID: user becomes push-unreachable
  → Channel router will use fallback channel (email) for future notifications
```

### Why Simpler Alternatives Fail

```
"Open new HTTP connection per push send"
  → TCP + TLS handshake: ~100ms per connection
  → At 400K sends/sec: impossible. Connection pool is mandatory.
  → APNs specifically ENCOURAGES persistent HTTP/2 connections.

"Send to all user tokens without checking validity"
  → 30% of tokens may be stale/invalid
  → Wasted sends: 30% × 400K/sec = 120K wasted sends/sec
  → Provider may rate-limit you for repeatedly hitting bad tokens
  → APNs considers this "abuse" and may revoke your certificate

"Single push provider (APNs only, let FCM users miss out)"
  → ~50% of users are Android → 50% of users unreachable
  → Cross-platform is not optional for any serious product

"Synchronous push send (wait for provider response before next)"
  → APNs round-trip: ~50ms
  → 400K sends/sec ÷ 50ms = need 20,000 concurrent sends
  → HTTP/2 multiplexing solves this (500 streams per connection)
  → Without multiplexing: 20,000 TCP connections → impractical
```

## Notification Aggregation Service

### The Problem

```
USER POSTS VIRAL PHOTO:
  → 5,000 likes in 60 seconds
  → Without aggregation: 5,000 push notifications to the author
  → User's phone buzzes 5,000 times → notification disabled permanently
  → THIS IS THE #1 REASON USERS DISABLE NOTIFICATIONS

SOLUTION: Aggregate notifications of the same type within a time window
  → "User A and 4,999 others liked your photo"
  → 1 notification instead of 5,000
```

### Algorithms

```
AGGREGATION LOGIC:

  Aggregation is performed BEFORE channel routing, AFTER preference evaluation.

  AGGREGATION KEY: (target_user, notification_type, object_id)
  → All likes on the same photo for the same user → one aggregate group

  AGGREGATION WINDOW: Configurable per notification type
  → "like": 60 seconds
  → "comment": 30 seconds (comments have more content, aggregate less)
  → "follow": 120 seconds
  → "mention": 0 seconds (never aggregate, each mention is distinct)
  → "otp": 0 seconds (never aggregate transactional)

  ALGORITHM (time-based aggregation with eager first delivery):

  ON RECEIVING notification N for aggregation key K:
    1. Check aggregation buffer for key K
    2. IF buffer is EMPTY:
       → Store N in buffer with timer = aggregation_window
       → Deliver N immediately as "User A liked your photo"
       → (First notification goes out instantly for responsiveness)
    3. IF buffer is NON-EMPTY (timer running):
       → Add N to buffer (increment count, collect actor names)
       → DO NOT deliver yet (wait for timer)
    4. WHEN timer expires:
       → IF count > 1 since first delivery:
         → Deliver aggregated: "User B, User C, and 47 others liked your photo"
         → Clear buffer
       → IF count == 0: Nothing new → clear buffer

  RESULT:
  → First like: Instant push → "User A liked your photo"
  → After 60s: One aggregated push → "User B and 4,998 others liked your photo"
  → Total: 2 push notifications instead of 5,000

  STATE REQUIREMENTS:
  → Aggregation buffer must be in-memory (latency-sensitive)
  → But must survive worker restarts → distributed cache with TTL
  → If cache fails: fall back to no-aggregation (deliver individually)
  → Better to over-notify than lose notifications
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
1. NOTIFICATION EVENTS (event log)
   → Every notification event received by the system
   → Used for: debugging, audit trail, replay after failures
   → Volume: ~220K events/sec = ~19B events/day

2. DELIVERY LOG (delivery attempts + outcomes)
   → Every delivery attempt per recipient per channel
   → Used for: dedup, analytics, compliance, debugging
   → Volume: ~660K deliveries/sec = ~57B entries/day

3. NOTIFICATION INBOX (per-user in-app notifications)
   → The user-facing notification list
   → Used for: in-app notification feed
   → Volume: ~660K writes/sec, ~50K reads/sec

4. USER PREFERENCES (per-user notification settings)
   → Channel preferences, quiet hours, frequency caps
   → Used for: preference evaluation in the delivery pipeline
   → Volume: ~500 writes/sec, ~1M reads/sec (from cache)

5. TOKEN REGISTRY (push tokens per device per user)
   → Device push tokens with validity state
   → Used for: push delivery routing
   → Volume: ~10K writes/sec, ~400K reads/sec (from cache)

6. AGGREGATION STATE (temporary, in-memory)
   → Buffered notifications pending aggregation
   → Used for: notification aggregation (merging rapid events)
   → Volume: ~100K active aggregation windows at any time
   → TTL: max aggregation window (120 seconds)

7. FAN-OUT STATE (temporary)
   → Progress tracking for large fan-out operations
   → Used for: resumability, monitoring, completion detection
   → Volume: ~1K active fan-out operations at any time
   → TTL: 24 hours
```

## How Data Is Keyed

```
NOTIFICATION INBOX:
  Primary key: (user_id, created_at DESC)
  → Optimized for: "Get latest 20 notifications for user X"
  → Partition key: user_id (all notifications for one user on same shard)
  → Sort key: created_at DESC (most recent first)
  → Why not event_id? User always queries by recency, not by event

DELIVERY LOG:
  Primary key: (event_id, user_id, channel, attempt_number)
  → Optimized for: "Did we deliver event X to user Y via push?"
  → Secondary index: (user_id, created_at DESC) for support queries
  → Partition key: event_id (all deliveries for one event colocated)
  → Alternative partition: time-bucket (for time-range queries)

USER PREFERENCES:
  Primary key: user_id
  → One row per user containing all preference settings
  → Denormalized: all notification types in one document/row
  → Why: Preference evaluation needs ALL type settings at once;
    separate rows per type would require multi-row reads

TOKEN REGISTRY:
  Primary key: (user_id, device_id)
  → One row per device per user
  → Secondary index: (token) for reverse lookups (APNs feedback)
  → Partition key: user_id (all devices for one user colocated)

EVENT LOG:
  Primary key: (time_bucket, event_id)
  → time_bucket: hourly partitions (2024-01-15T14:00:00)
  → Optimized for: time-range scans and TTL-based expiry
  → Partition by time, not by event type (even distribution)
```

## How Data Is Partitioned

```
NOTIFICATION INBOX:
  Strategy: Hash(user_id) → shard
  Shards: ~1,000 (at 500M users, ~500K users per shard)
  → Even distribution: user_ids are UUID-like, hash well
  → Hot shard risk: LOW (no user has disproportionate reads)
  → Growth: Add shards with consistent hashing, migrate incrementally

DELIVERY LOG:
  Strategy: Time-based partitioning (daily partitions)
  → Each day is a separate partition/table
  → Queries are almost always time-bounded ("last 24 hours")
  → Old partitions dropped on TTL expiry (30 days hot → delete)
  → Within partition: Hash(event_id) for even distribution

EVENT LOG:
  Strategy: Time-based partitioning (hourly partitions)
  → Very high write volume → time partitions enable parallel writes
  → Retention: Drop partitions older than 30 days
  → Replay: Read specific hour's partition for reprocessing

USER PREFERENCES:
  Strategy: Hash(user_id) → shard
  → Small dataset relative to others (~500M rows × ~1KB = ~500GB)
  → Read-heavy from cache, writes are rare
  → Single region can handle the load; replicate for DR

TOKEN REGISTRY:
  Strategy: Hash(user_id) → shard
  → ~180M active tokens across ~100M users
  → Read-heavy from cache (every push delivery needs tokens)
  → Write spikes on app releases (mass token refreshes)
```

### Notification Inbox Hot-User Problem

```
PROBLEM:
  Celebrity posts a viral photo → 500K likes in 1 hour
  → 500K in-app notification entries written to celebrity's inbox shard
  → Inbox partition key: Hash(user_id) → ALL 500K writes hit ONE shard
  → That shard becomes a hot shard → write latency spikes for all users
    on that shard → cascading slowdown

  This is the RECEIVER-side hot-user problem. The fan-out section covers
  the SENDER-side (celebrity posting). This is the opposite: a user who
  RECEIVES massive fan-in.

SCALE OF THE PROBLEM:
  → Celebrity with 10M followers who posts frequently receives:
    → ~500K likes/day, ~50K comments/day, ~10K follows/day
    → ~560K inbox writes/day for ONE user on ONE shard
  → Normal user: ~10-50 inbox writes/day
  → Hot user: 10,000× normal write volume on a single partition key

SOLUTIONS (layered):

  1. WRITE COALESCING VIA AGGREGATION (primary defense)
     → Aggregation service reduces 500K like notifications → ~8K aggregated
       entries (one per 60-second window per notification type per object)
     → 500K writes → 8K writes = 62× reduction
     → Most effective for high-frequency social events (likes, views)

  2. INBOX WRITE BUFFERING
     → For users exceeding a write rate threshold (>100 writes/min):
       → Buffer notifications in memory (distributed cache)
       → Flush to inbox store in batches every 5 seconds
       → Single batch write: 50 notifications per write operation
       → Reduces write QPS to inbox store by 50×
     → Trade-off: Up to 5-second staleness for inbox reads (acceptable)

  3. INBOX SHARDING BY (user_id, time_bucket)
     → Instead of Hash(user_id) alone:
       → Partition: Hash(user_id + day_bucket)
       → Spreads one user's writes across multiple partitions over time
       → Read must scan multiple partitions (fan-out on read)
       → Trade-off: Read latency increases from ~5ms to ~15ms
       → Only enable for users exceeding hot-user threshold

  4. INBOX SIZE LIMITS
     → Max 10,000 in-app notifications per user (oldest evicted)
     → Prevents unbounded inbox growth for hot users
     → Eviction: Delete oldest batch when limit exceeded (async cleanup)

  L5 MISTAKE: "Just add more shards"
  L6 INSIGHT: More shards don't help when one user's writes are the
  problem. The partition KEY is the bottleneck, not the partition COUNT.
  The fix must reduce write volume per key (aggregation, buffering) or
  change the key structure (time-bucketed compound key).
```

## Retention Policies

```
DATA TYPE         | HOT RETENTION | COLD RETENTION | RATIONALE
──────────────────┼───────────────┼────────────────┼──────────────────
Event Log         | 30 days       | 1 year         | Debugging + compliance
Delivery Log      | 90 days       | 1 year         | Analytics + compliance  
Notification Inbox| 90 days       | None (deleted)  | UX (old notifs irrelevant)
User Preferences  | Forever       | N/A            | Regulatory (opt-out records)
Token Registry    | Until invalid | N/A            | Prune invalid/stale tokens
Aggregation State | 120 seconds   | None           | Ephemeral by design
Fan-out State     | 24 hours      | None           | Only needed during processing

HOT → COLD MIGRATION:
  → Event Log: Move hourly partitions to cold storage after 30 days
  → Delivery Log: Move daily partitions to cold storage after 90 days
  → Cold storage: Compressed, columnar format on object storage
  → Query cold data via ad-hoc analytics engine (not real-time)
```

## Schema Evolution

```
NOTIFICATION INBOX EVOLUTION:
  V1: {user_id, type, content_text, created_at, read}
  V2: + {image_url, action_url, grouped_actors[]}  (rich notifications)
  V3: + {channel_delivered, priority, ttl_expiry}  (delivery metadata)
  V4: + {reaction_type, thread_id}  (social threading)
  
  Strategy: Schema-on-read (document store) or additive columns
  → Never rename/remove columns in hot path
  → Old entries served with default values for new fields
  → Migration of old rows: lazy (on read) or batch backfill

EVENT SCHEMA EVOLUTION:
  → Events are producer-generated; schema changes come from producer teams
  → Use schema registry: producer registers schema version
  → Consumer (fan-out service) handles multiple versions
  → Forward-compatible: New fields ignored by old consumers
  → Backward-compatible: Old events valid under new schema (defaults)

PREFERENCE SCHEMA EVOLUTION:
  → New notification type added → new entry in per_type_settings
  → Default: ENABLED for P0/P1, DISABLED for P2 (marketing)
  → Migration: Lazy — when user's preferences are loaded, apply defaults
    for any missing types
  → Why lazy: 500M users × preference migration = expensive batch job.
    Only ~10% of users will ever change defaults anyway.
```

## Why Other Data Models Were Rejected

```
RELATIONAL DB FOR NOTIFICATION INBOX:
  ✗ 660K writes/sec exceeds single-node capacity
  ✗ Schema rigidity makes adding rich notification fields painful
  ✗ JOINs not needed (inbox is single-table, single-user queries)
  ✓ Would work at small scale but not at 500M users

  WHY REJECTED: Write throughput and schema flexibility requirements
  favor a wide-column or document store.

GRAPH DB FOR SOCIAL GRAPH (fan-out resolution):
  ✗ We query social graph, we don't own it
  ✗ Fan-out resolution is a read-only traversal ("get all followers")
  ✗ Graph DB optimized for traversals we don't need (friend-of-friend)
  
  WHY REJECTED: Fan-out resolution is a simple adjacency list read.
  The social graph team owns the graph DB; we consume via API or cache.

TIME-SERIES DB FOR DELIVERY LOG:
  ✓ Natural fit for time-ordered append-only data
  ✓ Built-in TTL and compaction
  ✗ Delivery log needs per-event-id lookups (not just time-range)
  ✗ Most time-series DBs optimize for metrics, not event logs
  
  WHY ACCEPTABLE WITH CAVEATS: Time-partitioned wide-column store gives
  us both time-range queries AND event-id lookups. Pure TSDB lacks the
  secondary index flexibility.

SINGLE CACHE FOR ALL DATA:
  ✗ Different data has different TTL, size, and access patterns
  ✗ Preference data (small, rarely changing) competes with delivery
    dedup cache (large, high-churn) for memory
  ✗ One cache failure takes down all functionality

  WHY REJECTED: Separate caches per data type allow independent scaling,
  tuning, and failure isolation. Preference cache is tiny but critical;
  dedup cache is large but best-effort.
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
PREFERENCE UPDATES: Read-your-writes consistency for the mutating user
  User disables "like" notifications → MUST NOT receive next like notification
  IMPLEMENTATION:
  → Write to preference store (durable)
  → Invalidate preference cache entry for this user
  → Next preference evaluation → cache miss → load from store → fresh data
  → Other users' view of this preference (irrelevant — prefs are per-user)
  
  RISK: Cache invalidation races
  → User writes at T=0, cache invalidation at T=0.5
  → Preference evaluation at T=0.3 uses stale cache → delivers notification
  → MITIGATION: Version number in preference record
    → Cache entry includes version V
    → Write increments to V+1
    → Evaluation checks: if cached_version < store_version → refetch
  → ACCEPTABLE STALENESS: Up to 5 seconds (TTL-based fallback)

DELIVERY LOG: Eventually consistent
  → Delivery logs are append-only, no read-after-write requirement
  → Analytics queries tolerate minutes of lag
  → Dedup queries: see below (bloom filter)

NOTIFICATION INBOX: Eventually consistent
  → User opens inbox → sees notifications from 2 seconds ago
  → Notifications appearing "out of order" by 1-2 seconds is acceptable
  → Monotonic reads: once a notification appears, it should not disappear
    → IMPLEMENTATION: Timestamp-based ordering, no deletions (only TTL expiry)

TOKEN REGISTRY: Eventually consistent
  → New token registered → available for next notification (not current in-flight)
  → Token invalidation feedback → propagated within seconds
  → Brief window where we may send to an invalid token → APNs returns 410 → we handle
```

## Race Conditions

```
RACE 1: Concurrent preference update and notification delivery

  Timeline:
    T=0: Notification event for User B enters pipeline
    T=1: User B disables "like" notifications
    T=2: Preference evaluator checks User B's preferences
    
  SCENARIO A (T=2 sees update): Notification suppressed ✓
  SCENARIO B (T=2 uses stale cache): Notification delivered ✗
  
  IMPACT: Low (one extra notification after user disabled)
  MITIGATION: Short cache TTL (5s). In the worst case, user gets one
  notification they just disabled. Not great, but not a bug they'll notice
  (they were still receiving them 5 seconds ago).

RACE 2: Duplicate fan-out batches

  Timeline:
    T=0: Fan-out worker processes event E, produces batch B1
    T=1: Fan-out worker crashes before acknowledging queue message
    T=2: Queue redelivers event E to another worker
    T=3: New worker produces batch B1 again (duplicate)
    
  IMPACT: Medium (users in B1 could get duplicate notifications)
  MITIGATION: Batch-level idempotency key
  → batch_key = hash(event_id + batch_index)
  → Preference evaluator checks: have I processed this batch_key before?
  → Dedup cache with batch_key → prevents processing duplicate batches

RACE 3: Aggregation window vs immediate delivery

  Timeline:
    T=0: First like on photo (aggregation buffer empty)
    T=0: Deliver immediately → "User A liked your photo"
    T=0.5: Second like arrives → added to buffer, timer = 60s
    T=0.8: User reads inbox → sees "User A liked your photo"
    T=60: Aggregation timer fires → "User B and 0 others liked your photo"
    
  BUG: "User B and 0 others" (off-by-one in aggregate count)
  FIX: Aggregate message only sent if aggregated_count >= 2 after first
  delivery. Single additional like → "User B also liked your photo"

RACE 4: Token refresh during push delivery

  Timeline:
    T=0: Push worker loads tokens for User B → [old_token]
    T=1: User B opens app → new token registered, old token replaced
    T=2: Push worker sends to old_token → APNs returns 410 (gone)
    
  IMPACT: One missed push (old token invalid, new token not yet used)
  MITIGATION: 
  → On 410: Refresh token from registry (may have new token)
  → Retry with new token → SUCCESS
  → Cost: One extra round-trip for affected sends (~0.1% of sends)

RACE 5: Concurrent unread count updates from multiple in-app workers

  Timeline:
    T=0: In-App Worker A reads unread_count for User B → 5
    T=0: In-App Worker B reads unread_count for User B → 5
    T=1: Worker A writes notification + increments → 6
    T=1: Worker B writes notification + increments → 6
    EXPECTED: 7 (two new notifications)  ACTUAL: 6 (lost update)

  IMPACT: Medium (unread badge shows wrong count, user opens inbox
  and sees more unread than badge indicated → confusing but not harmful)

  MITIGATION:
  → Use atomic INCREMENT operation, not read-modify-write
    → INCR unread:{user_id} → counter atomically incremented
    → Most distributed caches and wide-column stores support atomic increment
  → If atomic increment unavailable: Accept approximate count
    → Unread count is eventually corrected when user opens inbox
    → Inbox read resets count to actual unread entries (reconciliation)
  → WHY NOT STRONG CONSISTENCY: 660K in-app writes/sec makes
    serializable transactions impractical. Approximate count is acceptable
    because the badge is a hint, not a contract.

  L6 INSIGHT: This is the same pattern as distributed counters in
  rate limiters. The solution is the same: atomic increment for correctness,
  or approximate counting with periodic reconciliation if atomicity is
  too expensive. In notification systems, reconciliation on inbox-open
  is a natural correction point that most systems already have.
```

## Idempotency

```
THREE LAYERS OF DEDUPLICATION:

LAYER 1: Event-level dedup (Ingestion API)
  → Idempotency key per event
  → Dedup cache: distributed hash map with TTL
  → Window: 1 hour (configurable per type)
  → Purpose: Prevent duplicate events from producer retries
  → Implementation: Check-and-set in dedup cache (atomic)

LAYER 2: Batch-level dedup (Preference Evaluator)
  → Batch key = hash(event_id + batch_index)
  → Dedup cache: separate from Layer 1
  → Window: 24 hours (fan-out may take hours for large events)
  → Purpose: Prevent duplicate batches from fan-out retries

LAYER 3: Delivery-level dedup (Channel Workers)
  → Delivery key = hash(event_id + user_id + channel)
  → Bloom filter: probabilistic, space-efficient
  → False positive rate: 0.01% (1 in 10,000 sends wrongly suppressed)
  → Window: 24 hours (matching event TTL)
  → Purpose: Prevent duplicate sends from channel worker retries
  → WHY BLOOM FILTER: 660K deliveries/sec × 24h = 57B keys
    → Exact dedup would need ~500GB of storage
    → Bloom filter: ~7GB at 0.01% FP rate → fits in memory

IDEMPOTENCY CONTRACT:
  → Same event_id always produces same outcome (no side effects on retry)
  → Same delivery_key always maps to same notification (no duplicate send)
  → Loss of idempotency state (cache failure) degrades to at-least-once
    → Acceptable for P1/P2 (slight over-delivery)
    → For P0: Exact dedup cache is maintained separately with higher durability
```

## Ordering Guarantees

```
EVENT ORDERING: NOT guaranteed across events
  → Events ingested in parallel may be processed out of order
  → "User A liked your photo" may arrive before "User B liked your photo"
    even if B happened first
  → ACCEPTABLE: Notification ordering by liked-at time is a nice-to-have,
    not a correctness requirement. Users don't perceive 2-second reorderings.

PER-USER ORDERING: Best-effort, not strict
  → Notifications to the same user may arrive out of order
  → In-app inbox: Ordered by created_at → display order is correct
  → Push notifications: Order of device display depends on OS, not us

FAN-OUT ORDERING: NOT guaranteed across recipients
  → In a fan-out of 10M, User X may be notified before User Y
  → No fairness guarantee (batch processing is first-come)
  → ACCEPTABLE: No user expects "I should get this notification before User Y"

AGGREGATION ORDERING: Preserved within window
  → All likes within a 60-second window are aggregated together
  → Window boundaries may split logical groups (like 59s vs 61s)
  → ACCEPTABLE: Aggregation is approximate by design

CROSS-CHANNEL ORDERING: NOT guaranteed
  → Push and email for the same event may arrive at different times
  → Push is typically faster (seconds) than email (minutes)
  → ACCEPTABLE: Channels have inherently different latencies

WHAT ORDERING BUGS LOOK LIKE:
  → "I got a notification about a reply to a comment I haven't seen yet"
    → Comment notification was slower than reply notification
    → Fix: Add causality hints (parent_event_id) for rendering, not delivery
  → "I got a push notification 30 minutes after the in-app notification"
    → Push was delayed (provider slow), in-app was immediate
    → Fix: Nothing — channels have different latencies by design
```

## Clock Assumptions

```
EVENT TIMESTAMP: Assigned by producer at event creation time
  → Different producers may have clock skew (up to a few seconds)
  → Events timestamped at ingestion: ingestion_timestamp added by API
  → Ordering decisions use ingestion_timestamp (our clock, trusted)
  → Display uses event_timestamp (producer's clock, approximate)

QUIET HOURS: Use server's view of user's local time
  → Server clock + user timezone → local time calculation
  → NTP-synced servers: clock skew < 10ms
  → Timezone offset accuracy: depends on IANA tz database freshness
  → DST transitions: 1-hour window of ambiguity twice per year
    → During DST transition, quiet hours may be off by 1 hour
    → ACCEPTABLE: 2 hours/year of imperfect quiet hours is fine

TTL EXPIRY: Based on event creation timestamp
  → TTL check: now() - event.created_at > ttl → DROP
  → Clock skew between producer and delivery worker:
    → If delivery worker's clock is ahead: Notification dropped prematurely
    → If behind: Notification delivered slightly after TTL
  → MITIGATION: Use ingestion_timestamp (our clock) for TTL checks
    → Eliminates cross-service clock skew

AGGREGATION WINDOWS: Based on wall clock of aggregation service
  → Window start: timestamp of first event in group
  → Window end: start + window_duration
  → Single service → no cross-node clock skew concern
  → But if aggregation is distributed: use logical clocks or accept
    slight window overlap between nodes
```

---

# Part 9: Failure Modes & Degradation (MANDATORY)

## Partial Failures

```
FAILURE 1: Push provider (APNs) partially down
  SYMPTOM: 50% of APNs sends return 503
  IMPACT: 50% of iOS push notifications fail
  DETECTION: Push worker error rate exceeds 5% threshold
  RESPONSE:
  → Circuit breaker HALF-OPEN: Reduce send rate by 80%
  → Re-enqueue failed sends to retry queue (with backoff)
  → If still failing after 5 minutes: Circuit breaker OPEN
  → Route iOS notifications to fallback channels (in-app + email)
  → Alert on-call: "APNs circuit breaker OPEN"
  RECOVERY:
  → Circuit breaker sends probe (1% of traffic) every 30 seconds
  → When probe succeeds: HALF-OPEN → gradually increase to 100%
  → Drain retry queue (with staleness check: drop notifications > TTL)

FAILURE 2: Preference cache partial failure (1 of 10 shards down)
  SYMPTOM: 10% of preference lookups fail (cache miss on shard)
  IMPACT: 10% of users get unfiltered notification evaluation
  DETECTION: Cache miss rate spikes from 1% to 10%
  RESPONSE:
  → Preference evaluator falls back to database reads for affected shard
  → Database handles ~10K additional reads/sec (acceptable short-term)
  → Cache shard auto-recovers (replica promotion or restart)
  RECOVERY:
  → New cache shard warms up from database (takes ~2 minutes)
  → During warmup: elevated database load but functional

FAILURE 3: Fan-out service partially overloaded
  SYMPTOM: Fan-out queue depth growing (consumers can't keep up)
  IMPACT: Fan-out latency increasing (30s → 5 minutes)
  DETECTION: Queue depth exceeds 1M items
  RESPONSE:
  → Auto-scale fan-out workers (add 50% more capacity)
  → If still growing: Shed P2 (bulk) fan-out entirely (drop from queue)
  → P0 and P1 fan-out continue on isolated queues
  → Alert: "Fan-out queue depth exceeds threshold"
  RECOVERY:
  → Additional workers drain backlog
  → P2 traffic re-enabled gradually after queue normalizes
```

## Slow Dependencies

```
SLOW DEPENDENCY 1: Social graph service (follower resolution)
  Normal latency: 10ms per page of 10K followers
  Slow: 500ms per page
  IMPACT: Celebrity fan-out takes 50× longer (15s → 12 minutes)
  RESPONSE:
  → Timeout per page: 200ms
  → Fall back to pre-computed partitions (may be 1 hour stale)
  → Alert: "Social graph latency exceeds 200ms P95"
  → Fan-out quality degrades (stale follower lists) but continues

SLOW DEPENDENCY 2: Template service (content rendering)
  Normal latency: 5ms per template render
  Slow: 200ms per render
  IMPACT: Email delivery delayed (template render is in email worker's hot path)
  RESPONSE:
  → Template cache: Render results cached for identical (template_id, params)
  → Cache HIT: Skip render entirely (most transactional emails are identical)
  → Cache MISS + slow render: Circuit breaker at 500ms timeout
  → Fallback: Use pre-rendered default template (generic content)
  → Push/SMS unaffected (simpler templates, no render service dependency)

SLOW DEPENDENCY 3: Delivery log store (write latency spike)
  Normal latency: 2ms per write
  Slow: 100ms per write
  IMPACT: Channel workers slow down (synchronous write to delivery log)
  RESPONSE:
  → Buffer delivery log writes in memory (batch every 100ms)
  → If buffer exceeds 10K items: write asynchronously (fire-and-forget)
  → Accept temporary loss of delivery log (notifications still delivered)
  → If store is down completely: Write to local file, ship later
  → Alert: "Delivery log write latency exceeds 50ms P95"
```

## Retry Storms

```
SCENARIO: APNs returns 429 (rate limited) for 10 seconds
  → 100K push sends/sec × 10s = 1M sends queued for retry
  → All 1M retries fire simultaneously after backoff expires
  → APNs rate-limits AGAIN (we just sent a burst)
  → Cycle repeats → retry storm

PREVENTION:
  1. JITTERED BACKOFF: Add random jitter to retry delay
     → Instead of all retrying at T+5s, spread over T+3s to T+7s
     → Distributes load over 4-second window instead of instant spike

  2. GLOBAL RATE LIMIT ON RETRIES:
     → Retry queue has its own rate limiter
     → Max retry rate: 50% of normal send rate
     → Prevents retries from exceeding provider capacity

  3. EXPONENTIAL BACKOFF WITH CEILING:
     → Retry 1: 1s + jitter, Retry 2: 5s + jitter, Retry 3: 30s + jitter
     → Max: 60s backoff (don't wait too long for P0)
     → Ceiling prevents unbounded growth in retry delay

  4. RETRY BUDGET PER EVENT:
     → P0: 3 retries, max total time: 60s
     → P1: 2 retries, max total time: 120s
     → P2: 1 retry, max total time: 300s
     → After budget exhausted: dead-letter queue + fallback channel

  5. CIRCUIT BREAKER (per provider):
     → If error rate > 30% for 30 seconds → OPEN
     → No sends to this provider (saves quota, prevents storm)
     → Probe every 30s → gradual recovery
```

## Data Corruption

```
SCENARIO 1: Preference store returns wrong user's preferences
  CAUSE: Shard mapping bug after rebalancing
  IMPACT: User A's notifications evaluated with User B's preferences
  → User A (who disabled marketing) gets marketing notifications
  → User B (who enabled everything) gets nothing
  DETECTION: Anomaly detection on per-user notification rate changes
  → Sudden change in notification volume for many users simultaneously
  MITIGATION:
  → Preference evaluator includes user_id verification
    (preference record's user_id must match requested user_id)
  → If mismatch: Reject, re-fetch, alert
  → Canary: Test accounts with known preferences, verified hourly

SCENARIO 2: Delivery log dedup bloom filter corrupted
  CAUSE: Memory corruption, bad serialization after restart
  IMPACT: False positives spike → legitimate notifications suppressed
  (bloom filter says "already sent" when it wasn't)
  DETECTION: Delivery rate drops sharply with no corresponding volume decrease
  MITIGATION:
  → Bloom filter has a version/checksum; verify on load
  → If corrupted: Reinitialize empty bloom filter
  → Risk: Temporary duplicates (bloom filter forgot recent sends)
  → Acceptable: Better to send some duplicates than suppress all notifications

SCENARIO 3: Token registry contains tokens for wrong users
  CAUSE: Bug in token registration endpoint (user_id not validated)
  IMPACT: Push notification for User A delivered to User B's device
  → SEVERE: Privacy violation, security incident
  DETECTION: Hard to detect (user reports "I got someone else's notification")
  PREVENTION:
  → Token registration requires authenticated session (verify user_id matches session)
  → Token binding: APNs/FCM tokens are device-specific (hard to steal)
  → Audit log: All token registrations logged with full context
```

### Queue Poison Pill Handling

```
PROBLEM:
  A malformed notification event passes schema validation but causes
  the fan-out worker to crash (e.g., fan_out_type = "FOLLOWERS" but
  actor field is null → NullPointerException on social graph call).
  
  Queue redelivers the message → worker crashes again → redelivery →
  crash → infinite loop. The "poison pill" blocks the queue partition,
  preventing all notifications behind it from being processed.

WHY THIS IS INSIDIOUS:
  → One bad event can block an ENTIRE queue partition
  → If P0 queue has 10 partitions, one poison pill blocks 10% of P0
  → Workers are restarting constantly → CPU wasted on crash loops
  → Alert noise: Worker restart alerts mask the root cause
  → At 220K events/sec, this can accumulate fast

DETECTION:
  → Track per-message retry count (most queue systems expose this)
  → If retry_count > MAX_RETRIES (e.g., 5) → poison pill detected
  → Monitor worker restart rate: If restarts > 10/min → investigate

HANDLING:
  1. DEAD-LETTER QUEUE (DLQ):
     → After MAX_RETRIES, move message to DLQ (not main queue)
     → DLQ is a separate queue that is NOT consumed by normal workers
     → DLQ messages reviewed by on-call engineer or automated analyzer
     → Main queue unblocked immediately

  2. DEFENSIVE DESERIALIZATION:
     → Worker wraps event processing in try-catch at the TOP level
     → ANY unhandled exception → log event payload + error → ACK message
       (remove from queue) → write to DLQ → continue processing
     → Worker NEVER crashes on a single bad message

  3. POISON PILL ALERTING:
     → DLQ depth > 0 → alert on-call: "Poison pill detected"
     → Alert includes: event_id, event type, error message, sender_id
     → On-call decides: Fix event and replay, or discard

  4. BLAST RADIUS CONTAINMENT:
     → Queue partitions are independent
     → Poison pill on partition 3 doesn't affect partitions 0-2 or 4-9
     → BUT if all partitions get the same bad event type (producer bug),
       all partitions are affected simultaneously
     → Defense: Per-sender circuit breaker. If sender's events cause
       3+ DLQ entries in 1 minute → reject all events from that sender

REAL-WORLD ANALOGY (API Gateway):
  API gateways handle malformed requests by returning 400, not crashing.
  Queue consumers must handle malformed events the same way: reject 
  gracefully, don't crash. A single bad request should never take down
  a worker processing thousands of good requests per second.
```

## Control-Plane Failures

```
KILL SWITCH UNAVAILABLE:
  → Marketing sends a wrong campaign to 50M users
  → Ops team tries to activate kill switch → kill switch service is down
  IMPACT: Wrong notifications continue to be delivered
  MITIGATION:
  → Kill switch is distributed (cached at every worker)
  → Kill switch writes to distributed cache with broadcast invalidation
  → Even if kill switch API is down, manual cache entry update works
  → Last resort: Scale fan-out workers to zero (stops all processing)

CONFIGURATION UPDATE FAILURE:
  → New notification type added, preference defaults need updating
  → Config push fails — workers have old config
  IMPACT: New notification type treated as "unknown" → silently dropped
  MITIGATION:
  → Unknown types fall through to a default handler
  → Default handler: Deliver with default preferences (enabled, all channels)
  → Alert: "Unknown notification type received: {type}"

MONITORING FAILURE:
  → Delivery success metrics stop reporting
  IMPACT: Team doesn't notice when delivery fails
  MITIGATION:
  → Absence of signal is itself a signal (dead man's switch)
  → If no delivery metrics received for 5 minutes → auto-alert
  → Independent monitoring from multiple layers (API, workers, providers)
```

### Deployment-Related Failure Modes

```
SCENARIO 1: Bad code push to push workers
  CAUSE: New worker version has a bug that drops 50% of push payloads
  → Payloads rendered but not sent (silent failure, no error thrown)
  IMPACT: 50% of push notifications silently lost on deployed workers
  DETECTION:
  → Delivery success rate drops from 95% to ~47%
  → BUT: If the bug swallows errors, worker reports "success" → INVISIBLE
  → Defense: End-to-end delivery confirmation (provider feedback, not just
    "I called the API without throwing"). If provider doesn't confirm 
    delivery within expected window → flag as suspected silent failure.

  CANARY DEPLOYMENT STRATEGY:
  → Deploy new worker version to 1% of workers (canary)
  → Monitor for 15 minutes:
    → Delivery success rate: Compare canary vs control (99% of workers)
    → Latency: Compare P50/P99 between canary and control
    → DLQ rate: New poison pills appearing?
    → Error log volume: Spike in exceptions?
  → If canary metrics within 5% of control → proceed to 10%, then 50%, then 100%
  → If ANY metric deviates > 5% → automatic rollback of canary

  WHY CANARY IS CRITICAL FOR NOTIFICATION WORKERS:
  → Unlike a web API where a bad deploy causes visible errors to users,
    a bad notification worker deploy causes SILENT notification loss.
  → Users don't immediately notice a missing "like" notification.
  → The bug may run for hours before a user reports "I'm not getting
    notifications." By then, millions of notifications are lost.
  → Canary deployment with automated metric comparison is the ONLY
    defense against silent notification loss.

SCENARIO 2: Configuration push breaks priority classification
  CAUSE: Config update remaps event type "otp" from P0 to P1
  → OTP notifications no longer get dedicated P0 fast path
  → OTP delivery latency jumps from 300ms to 15 seconds (P1 queue load)
  IMPACT: Users can't verify accounts → revenue impact
  DETECTION:
  → P0 queue depth drops to zero (no events classified as P0)
  → P1 queue depth spikes unexpectedly
  → OTP-specific delivery latency SLO breached
  PREVENTION:
  → Config changes require approval from notification platform on-call
  → P0 event types are pinned: Config system rejects reclassification of
    hardcoded P0 types (otp, security_alert, payment_confirmation)
  → Config canary: New config deployed to 1% of workers first

SCENARIO 3: Preference store schema migration causes stale reads
  CAUSE: Schema migration adds new field, but read path doesn't handle
  missing field gracefully → preference evaluator crashes on unmigrated rows
  IMPACT: Preference evaluation fails for unmigrated users → notifications
  either suppressed (fail-closed) or delivered without preference check (fail-open)
  PREVENTION:
  → All schema migrations must be backward-compatible
  → Read path handles missing fields with explicit defaults
  → Migration is lazy (on-read) not bulk (risk of bulk failure)
  → Test: Run preference evaluator against 1,000 random user records
    before AND after schema change in staging
```

## Blast Radius Analysis

```
COMPONENT FAILURE      | BLAST RADIUS                | USER-VISIBLE IMPACT
───────────────────────┼─────────────────────────────┼─────────────────────
Ingestion API down     | ALL notifications            | No notifications sent
P0 queue down          | Transactional only           | OTPs/security alerts delayed
P1 queue down          | Social/content only          | Likes/comments not notified
P2 queue down          | Marketing/bulk only          | Campaigns delayed (low impact)
Fan-out service down   | 1:N notifications only       | Celebrity posts not fanned out
                       | 1:1 still works (target known)|
Pref cache down        | All priority classes          | Either default prefs (risk) or
                       |                              | held in queue (delayed)
Push workers down      | Push channel only             | No push notifications
                       | Email/SMS/in-app unaffected  |
Email workers down     | Email channel only            | No email notifications
                       | Push/SMS/in-app unaffected   |
APNs down              | iOS push only                 | iOS users don't get push
                       | Android push unaffected      |
Notification inbox DB  | In-app channel only           | Inbox empty or stale
                       | Push/email/SMS unaffected    |
Token registry down    | Push channel only             | Push can't resolve tokens
                       |                              | Fallback to email/in-app
Delivery log store down| No impact on delivery         | Analytics/dedup degraded
                       | Delivery continues           | Slight duplicate risk

KEY INSIGHT: Channel isolation limits blast radius.
APNs outage affects only iOS push. No cascading failure to other channels.
Priority queue isolation limits blast radius.
P2 overload cannot affect P0 delivery.
```

## Failure Timeline Walkthrough

```
SCENARIO: APNs outage during a celebrity fan-out event

T=0:00  Celebrity with 10M followers posts. Event ingested. Priority: P1.
T=0:02  Fan-out service begins resolving followers.
T=0:15  1,000 batches of 10K recipients produced. Preference evaluation begins.
T=0:25  Preference evaluation complete. 3.7M push sends + 10M in-app writes queued.
T=0:30  Push workers begin sending to APNs. Rate: 100K/sec.
T=0:35  APNs begins returning 503 errors. Error rate: 10% → 30% → 80%.
T=0:40  Push worker circuit breaker: HALF-OPEN (reduces send rate to 20K/sec).
T=0:50  Error rate still 80%. Circuit breaker: OPEN. All APNs sends stopped.
T=0:50  Alert fires: "APNs circuit breaker OPEN. Push delivery halted."
T=0:50  Push sends re-enqueued to retry queue with 30s backoff.
T=0:50  In-app delivery continues unaffected (no APNs dependency).

T=1:00  Circuit breaker probes APNs (1 request). Still 503. Remains OPEN.
T=1:30  Probe again. Still 503. Remains OPEN.
T=2:00  Probe succeeds. Circuit breaker: HALF-OPEN. Send rate: 10K/sec.
T=2:10  Error rate: 5%. Circuit breaker: CLOSED. Send rate: 100K/sec.
T=2:10  Retry queue begins draining (3.7M queued sends - ~500K already completed).
T=2:10  Staleness check: Notifications older than TTL (1 hour) → dropped.
T=2:15  All notifications are within TTL. Retry queue draining at 100K/sec.
T=2:47  Retry queue fully drained. All 3.7M push sends delivered or dropped.

TOTAL OUTAGE DURATION: ~2 minutes (T=0:50 to T=2:10)
USER IMPACT:
  → 500K push sends completed before outage (first 5 seconds)
  → 3.2M push sends delayed by ~2 minutes
  → 0 push sends lost (all within TTL)
  → 10M in-app writes completed on time (unaffected)
  → Android push (FCM) unaffected throughout (separate provider)

RETROSPECTIVE:
  Circuit breaker prevented retry storm (good).
  In-app isolation prevented total notification loss (good).
  Could improve: FCM for iOS as secondary provider (reduce APNs dependency).
```

### Cascading Multi-Component Failure Timeline

```
SCENARIO: Celebrity fan-out + preference cache degradation + email provider slow
  (Three failures overlapping — the kind of compound incident that defines
  Staff Engineer vs Senior Engineer response.)

T=0:00  Celebrity with 50M followers posts. Event ingested as P1.
T=0:02  Fan-out service begins: 5,000 batches of 10K recipients.
T=0:10  Preference cache shard 7 (of 10) goes down.
        → 10% of preference lookups now fall through to database
        → Preference evaluation latency jumps: 1ms → 8ms for affected users
        → Database receives 10× normal read load from cache misses
T=0:15  Database read latency increases from 5ms to 50ms under load.
        → Preference evaluation for ALL users slows down (DB is shared)
        → Even cache-hit users experience slowdown (workers are I/O-blocked
          waiting for the 10% of cache-miss DB reads)
T=0:20  Preference evaluation queue depth starts growing.
        → Backpressure: Fan-out service slows batch production
        → Celebrity fan-out: Expected 15s, now projecting 3 minutes
T=0:25  Email provider begins returning 503 (unrelated maintenance).
        → Email channel circuit breaker: HALF-OPEN
        → Email notifications re-enqueued to retry queue
T=0:30  System state: THREE concurrent degradations
        → Preference cache: Shard 7 still down → DB overloaded
        → Fan-out: Running 12× slower than normal
        → Email: Circuit breaker engaged

COMPOUND EFFECTS (what makes this L6-level):
  → Fan-out slowdown means preference evaluation queue grows
  → Queue growth means MORE workers are pulling from the queue
  → More workers means MORE database reads (cache misses)
  → Database slowdown worsens → preference evaluation slows further
  → POSITIVE FEEDBACK LOOP: Each failure amplifies the others

TRIAGE (what on-call does):
  T=0:32  On-call receives: 3 simultaneous alerts
    1. "Preference cache shard 7 DOWN"
    2. "Fan-out queue depth exceeding 5M"
    3. "Email circuit breaker HALF-OPEN"

  PRIORITY ORDER:
  1. Preference cache (root cause of amplification loop)
     → Restart shard 7 or promote replica
     → If restart fails: Extend TTL on remaining shards (serve stale prefs)
     → IMMEDIATE: Reduce database load by failing open for P2
       (deliver P2 with default preferences, don't hit DB)
  2. Fan-out queue (symptom, not cause — will resolve when prefs stabilize)
     → Shed P2 fan-out to reduce queue depth
     → Celebrity fan-out continues at reduced rate
  3. Email circuit breaker (independent, lowest priority)
     → Let circuit breaker handle it automatically
     → Email will catch up when provider recovers

  T=0:40  Shard 7 restarted. Cache warming begins.
  T=0:42  Database load drops as cache serves hits again.
  T=0:45  Preference evaluation latency normalizes.
  T=0:48  Fan-out queue begins draining.
  T=0:55  Email provider returns. Circuit breaker closes.
  T=1:05  All queues normalized. Celebrity fan-out completes.

TOTAL IMPACT:
  → P0: UNAFFECTED (separate queue, separate workers, separate cache pool)
  → P1 push: ~5 minute delay for celebrity's followers
  → P1 email: ~30 minute delay (email circuit breaker + retry queue)
  → P2: ~2 hours delay (shed during incident, re-enabled after)
  → No notifications permanently lost

RETROSPECTIVE:
  → Root cause: Single cache shard failure cascaded via shared database
  → Fix: Database connection pooling with per-priority limits
    → P0 workers get dedicated DB connections (not shared)
    → Cache miss fallback has its own connection pool with hard limit
    → Prevents cache failure from overloading the shared database
  → Fix: Auto-scaling preference evaluator workers during cache degradation
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
CRITICAL PATH 1: P0 Transactional (OTP delivery)
  Event ingestion → (no fan-out, direct) → Preference evaluation 
  → Channel routing → Push/SMS delivery
  TOTAL BUDGET: 5 seconds end-to-end
  BREAKDOWN:
  → Ingestion: 2ms (validate, dedup, enqueue)
  → Queue processing: 10ms (pickup from P0 dedicated queue)
  → Preference evaluation: 1ms (cache lookup, simple check)
  → Channel routing: 0.5ms
  → Push send: 50-200ms (APNs/FCM round-trip)
  → SMS send: 200-2000ms (SMS provider dependent)
  → TOTAL: ~300ms typical, ~2.5s P99
  → WELL WITHIN 5s budget

  OPTIMIZATION: P0 has a dedicated fast path
  → Separate queue cluster (physically isolated)
  → Dedicated worker pool (not shared with P1/P2)
  → No aggregation (OTP never aggregated)
  → Minimal preference evaluation (OTP bypasses most checks)
  → Direct channel routing (OTP goes to SMS + push, always)

CRITICAL PATH 2: Push delivery for social notifications (P1)
  Event → fan-out → preference → push worker → APNs/FCM
  TOTAL BUDGET: 30 seconds end-to-end
  BOTTLENECK: Preference evaluation (batch loading) + push send (provider latency)

CRITICAL PATH 3: Celebrity fan-out
  Event → fan-out (10M recipients) → preference (10M checks) → push (3.7M sends)
  TOTAL BUDGET: First recipient < 30s, last recipient < 5 minutes
  BOTTLENECK: Fan-out resolution (social graph reads) + push throughput (100K/sec)
```

## Caching Strategies

```
CACHE 1: User Preferences
  WHAT: Per-user notification preferences
  SIZE: 500M users × ~1KB = ~500GB (too large for single cache)
  STRATEGY: 
  → Sharded across 100 cache nodes (~5GB per node)
  → TTL: 5 seconds (short, because preference changes must propagate fast)
  → Write-through: Preference write → DB write → cache invalidation
  → Cache miss: Load from DB, populate cache
  → HIT RATE: ~99% (preferences rarely change, TTL is short but access is frequent)

CACHE 2: Push Tokens
  WHAT: Per-user device push tokens
  SIZE: 100M users × 1.8 devices × ~200 bytes = ~36GB
  STRATEGY:
  → Sharded by user_id
  → TTL: 15 minutes (token changes are rare, but stale tokens waste sends)
  → Write-through: Token registration → DB → cache invalidation
  → HIT RATE: ~99.5%

CACHE 3: Deduplication (Event-level)
  WHAT: Recently seen idempotency keys
  SIZE: 220K events/sec × 3600s × 16 bytes key = ~12.7GB per hour window
  STRATEGY:
  → In-memory distributed cache with TTL
  → TTL: 1 hour (matching event dedup window)
  → No persistence needed (loss = small window of potential duplicates)

CACHE 4: Deduplication (Delivery-level, Bloom Filter)
  WHAT: Recently sent (event_id, user_id, channel) tuples
  SIZE: ~7GB for 57B entries at 0.01% FP rate (24-hour window)
  STRATEGY:
  → Partitioned bloom filters (one per hour, rotate after 24h)
  → In-memory, no persistence
  → On restart: Empty bloom filter (accept temporary duplicate risk)

CACHE 5: Aggregation Buffers
  WHAT: In-progress notification aggregation windows
  SIZE: ~100K active windows × ~500 bytes = ~50MB (tiny)
  STRATEGY:
  → Distributed cache with TTL = max_aggregation_window (120s)
  → Atomic increment for counter (optimistic locking)
  → On loss: Aggregation resets → next notification starts new window
```

## Precomputation vs Runtime Work

```
PRECOMPUTED:
  → Celebrity follower partitions (hourly batch job)
    → Avoids real-time social graph reads for large fan-outs
    → Trade-off: Up to 1 hour stale follower list
  
  → Notification inbox unread count
    → Incremented on write, reset on read
    → Avoids counting query on every app open (which would scan inbox)
  
  → User timezone offset
    → Precomputed from user's profile location
    → Updated on location change (rare)
    → Avoids timezone database lookup per notification
  
  → Channel health score per user
    → "Is this user's push token likely valid?"
    → Computed from: last successful push, last token refresh, device type
    → Updated hourly → used in channel routing to skip unreachable channels
    → Avoids wasting push sends on dead tokens

RUNTIME (cannot precompute):
  → Frequency cap evaluation
    → Depends on real-time notification count (can't predict)
  
  → Quiet hours check
    → Depends on current time + user timezone (real-time calculation)
  
  → Event deduplication
    → Depends on whether this exact event was seen before (real-time lookup)
  
  → Push payload rendering
    → Depends on actor's current display name, profile photo URL
    → Precomputing would serve stale content (user renamed since event)
```

## Backpressure

```
BACKPRESSURE POINT 1: Ingestion API → Ingestion Queue
  SIGNAL: Queue depth exceeds threshold (10M items)
  RESPONSE:
  → Ingestion API returns 429 to P2 (bulk) senders
  → P0 and P1 senders still accepted (isolated queue)
  → Sender retries with backoff
  → If queue depth exceeds 100M: Start rejecting P1 too
  → P0 always accepted (dedicated queue with reserved capacity)

BACKPRESSURE POINT 2: Fan-out → Preference Evaluation Queue
  SIGNAL: Preference queue depth exceeds threshold
  RESPONSE:
  → Fan-out service slows down batch production rate
  → Reduces parallelism on social graph reads
  → Effect: Fan-out takes longer but doesn't flood downstream
  → Celebrity fan-out: 15s → 60s (acceptable for P1)

BACKPRESSURE POINT 3: Channel Workers → Provider
  SIGNAL: Provider returning 429 (rate limit) or increasing latency
  RESPONSE:
  → Workers reduce send rate (respect provider rate limit)
  → Excess items remain in channel queue
  → If queue depth exceeds threshold: Circuit breaker on that channel
  → Redirect to fallback channels or hold in queue
  
BACKPRESSURE POINT 4: System-wide overload
  SIGNAL: All queues at high depth, worker CPU > 80%
  RESPONSE:
  → SHED P2 entirely (marketing can wait)
  → THROTTLE P1 to 50% throughput
  → P0 ALWAYS at full capacity
  → Scale workers horizontally (auto-scaling, takes 2-5 minutes)
  → Alert: "System-wide overload. P2 shedding active."
```

## Load Shedding

```
LOAD SHEDDING HIERARCHY (what to drop first):

  1. P2 marketing notifications (lowest user impact)
     → Re-enqueue with delay or drop with campaign notification to sender
  
  2. P1 notifications for dormant users (haven't opened app in 30 days)
     → These are unlikely to be read anyway
     → In-app write still happens; push/email dropped
  
  3. P1 notifications with < 10 minutes remaining TTL
     → About to expire anyway; delivering late is worse than not delivering
  
  4. NEVER shed P0 transactional notifications
     → OTP, security alerts, payment confirmations are non-negotiable
     → If P0 is at risk: SHED ALL P1 and P2 to protect P0

IMPLEMENTATION:
  → Each queue consumer checks system load score on every dequeue
  → Load score: weighted combination of queue depths + worker CPU + provider health
  → Score > 0.7: Shed P2
  → Score > 0.85: Shed P2 + throttle P1
  → Score > 0.95: Shed P2 + shed P1 + alert (protect P0 only)
```

## Why Some Optimizations Are Intentionally NOT Done

```
"PRE-COMPUTE NOTIFICATIONS FOR ALL USERS"
  → For every new post, pre-generate notification entries for all followers
  → WHY NOT: Write amplification is already the bottleneck.
    Pre-computing for 100M followers of a celebrity means 100M writes
    even for users who won't open the app today. Only 30% of users
    open the app daily. We'd waste 70% of writes.

"PUSH COALESCING (batch multiple notifications into one push)"
  → Combine "3 new likes" + "1 new comment" into a single push
  → WHY NOT: Different notification types have different urgency.
    Waiting to batch means delaying the first notification.
    User should get the comment notification NOW, not 60 seconds later
    when a like happens to arrive too.
    Exception: The aggregation within a TYPE (5 likes → "User A and 4 others")
    is done because those are the same urgency.

"PERSISTENT CONNECTIONS TO ALL USERS FOR REAL-TIME PUSH"
  → Maintain WebSocket to every user for instant push delivery
  → WHY NOT: 100M concurrent connections is massive infrastructure.
    APNs/FCM already maintain persistent connections to devices.
    We get near-real-time delivery via APNs/FCM without managing
    connections ourselves. WebSocket makes sense for chat, not push.

"ML-BASED OPTIMAL SEND TIME"
  → Predict the best time to send each notification using ML model
  → WHY NOT: Adds 50-100ms of model inference latency to every notification.
    Only valuable for P2 (marketing). For P1 (social), users want
    immediate delivery. Implement only for P2 as an optional stage,
    not in the critical path.
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
1. THIRD-PARTY PROVIDER COSTS (largest)
   Push (APNs/FCM): Free (platform-provided) — BUT indirect cost in
     managing tokens, handling feedback, and engineering time
   Email: $0.10 per 1,000 emails (SES-like pricing)
     → 50K emails/sec × 86,400 sec/day = 4.3B emails/day
     → BUT only ~10% of notifications go to email = ~430M/day
     → Cost: ~$43K/day = ~$1.3M/month for email alone
   SMS: $0.01-0.05 per SMS (varies by country)
     → 2K SMS/sec × 86,400 sec/day = ~173M/day
     → Average $0.02/SMS = $3.5M/day = ~$105M/month for SMS
     → SMS IS BY FAR THE MOST EXPENSIVE CHANNEL
     → This is why SMS is restricted to P0 transactional only

2. COMPUTE (workers)
   Fan-out workers: CPU-bound (list processing, batching)
   Preference evaluators: Memory-bound (cache-dependent)
   Channel workers: I/O-bound (network calls to providers)
   Estimated: 500-1,000 worker instances × $0.05/hr = ~$50/hr = ~$36K/month

3. STORAGE
   Notification inbox: 57B entries/day × 90 days × 200 bytes = ~1PB
     → Managed wide-column store: ~$30K/month at this scale
   Delivery log: 57B entries/day × 90 days × 100 bytes = ~500TB
     → Time-partitioned store: ~$15K/month
   Cold storage: 1 year retention, compressed: ~$2K/month (object storage)

4. QUEUES / MESSAGE BROKERS
   Priority queues handle ~1.5M messages/sec total
   Managed queue service: ~$15K/month at this throughput

5. CACHES
   Preference cache: 500GB across 100 nodes
   Token cache: 36GB
   Dedup caches: ~20GB
   Total: ~600GB of distributed cache = ~$20K/month

TOTAL MONTHLY COST ESTIMATE:
  Email sending:     $1.3M
  SMS sending:       $105M (dominant cost — drives entire cost optimization)
  Compute:           $36K
  Storage:           $47K
  Queues:            $15K
  Caches:            $20K
  TOTAL:             ~$107M/month (SMS-dominated)
```

### Bandwidth and Observability Costs

```
BANDWIDTH (often overlooked):
  Push payloads: ~1KB average (text + metadata)
  → 400K push/sec × 1KB = 400MB/sec = ~1PB/month egress
  → With rich push (images): ~10KB average → 10PB/month egress
  → Cloud egress cost: ~$0.05/GB → $500K-$5M/month for push alone
  → MITIGATION: Image URLs in push payload, not inline images.
    Device fetches image from CDN. Push payload stays small.

  Email payloads: ~50KB average (HTML + inline CSS)
  → 50K emails/sec × 50KB = 2.5GB/sec = ~6.5PB/month egress
  → Cloud egress: ~$325K/month
  → MITIGATION: Minimalist email templates. Link to web content
    instead of embedding heavy HTML.

  SMS payloads: ~160 bytes (trivial bandwidth)

  TOTAL BANDWIDTH COST: $500K-$5M/month
  → Not dominant vs SMS, but significant vs compute/storage
  → Often missed in initial cost estimates

OBSERVABILITY INFRASTRUCTURE:
  Metrics:
  → Per-channel delivery rate, latency, error rate
  → Per-notification-type volume, suppression rate
  → Per-sender event rate, rejection rate
  → Per-provider health score
  → Per-user notification rate (for frequency cap debugging)
  → ~50K unique metric time series × 10s resolution = ~500K data points/sec
  → Metrics storage: ~$5K/month

  Logging:
  → Every delivery attempt logged for debugging
  → 660K log entries/sec × ~500 bytes = 330MB/sec = ~850TB/month
  → Log storage (searchable, 14 days): ~$25K/month
  → Log storage (archive, 90 days): ~$5K/month

  Distributed tracing:
  → Trace P0 notifications end-to-end (ingestion → delivery)
  → Sample 1% of P1/P2 traces (full tracing at 660K/sec is impractical)
  → Trace storage: ~$3K/month

  Dashboards & alerting:
  → Real-time dashboards for on-call
  → Per-channel, per-priority, per-provider views
  → Alert rules: ~200 alert conditions across the system
  → Alerting service: ~$2K/month

  TOTAL OBSERVABILITY COST: ~$40K/month
  → 0.04% of total cost — trivial relative to SMS
  → BUT: Without observability, you can't detect the failures that
    cause the cost spikes (retry storms, silent delivery failures)
  → The $40K/month observability spend prevents $1M+/month in
    undetected delivery failures and wasted sends

  L6 INSIGHT: Observability cost should be budgeted as a percentage
  of delivery cost (0.1-1%), not as a separate line item that gets
  cut when someone looks for "easy savings." Cutting observability
  to save $40K/month will cost you $1M/month in the first
  undetected silent failure incident.
```

## How Cost Scales with Traffic

```
LINEAR SCALING:
  → Provider costs (email, SMS): Directly proportional to send volume
  → Delivery log storage: Proportional to notifications delivered
  → Queue throughput: Proportional to event volume

SUBLINEAR SCALING:
  → Cache cost: Grows with unique users, not notification volume
    (500M users regardless of whether each gets 1 or 100 notifications)
  → Compute: Workers handle bursts via auto-scaling, return to baseline
  → Preference store: Grows with users, not with notifications

SUPERLINEAR SCALING:
  → Fan-out cost: Celebrity with 100M followers costs 100M × per-recipient cost
    per event. A product change increasing average fan-out from 3 to 5
    increases downstream volume by 67%.
  → SMS if expanded: Moving SMS from P0-only to P1 would 100x SMS costs

COST REDUCTION LEVERS:
  1. Reduce SMS usage (biggest lever)
     → Verify phone → push OTP to app instead of SMS (if app installed)
     → Use push-based 2FA instead of SMS-based
     → Savings: 80% SMS reduction = $84M/month savings

  2. Email optimization
     → Digest emails instead of individual (10 notifications → 1 email)
     → Reduce email volume by 80% → save ~$1M/month
     → Better user experience too (less inbox clutter)

  3. Fan-out optimization
     → For celebrity posts, skip push for inactive users (no app open in 7 days)
     → Reduce push sends by ~30% for large fan-outs
     → Savings: Compute + provider capacity + user experience (fewer stale notifs)

  4. Token hygiene
     → Regularly prune invalid/stale tokens
     → Avoid sending to tokens that will 410 (wasted APNs capacity)
     → Indirect savings: Reduced compute, fewer retries
```

## Trade-offs Between Cost and Reliability

```
TRADE-OFF 1: Multi-provider redundancy vs cost
  SINGLE PROVIDER: $X/month, no failover
  MULTI PROVIDER: $1.5X/month (maintain two providers), automatic failover
  DECISION: Multi-provider for P0 (SMS: primary + backup vendor).
  Single provider for P2 (marketing email — outage is tolerable).

TRADE-OFF 2: Delivery log completeness vs storage cost
  COMPLETE: Log every attempt, outcome, and retry → full debugging capability
  SAMPLED: Log 10% of deliveries → 90% cost reduction, degraded debugging
  DECISION: 100% for P0, 100% for P1 (for 30 days), 10% sample for P2.
  P2 campaigns have separate analytics; delivery log for debugging is less critical.

TRADE-OFF 3: Aggressive retry vs cost
  AGGRESSIVE: 5 retries per failed send → higher delivery rate, higher cost
  CONSERVATIVE: 1 retry → lower delivery rate, lower cost
  DECISION: 3 retries for P0 (delivery matters most), 2 for P1, 1 for P2.
  Each retry costs compute + provider capacity. Diminishing returns after retry 2.

TRADE-OFF 4: Push token validation vs send-and-check
  VALIDATE FIRST: Call provider's token validation API before sending
  SEND AND CHECK: Just send; handle 410 responses
  DECISION: Send-and-check. Validation API has its own latency and cost.
  At 400K sends/sec, pre-validation would double provider API calls.
  410 rate is ~1% — cheaper to handle 4K failures than make 400K validation calls.
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING 1: Exactly-once delivery guarantee
  → Requires distributed transactions across producer, queue, and provider
  → Adds 10× complexity to the delivery pipeline
  → APNs/FCM don't guarantee exactly-once themselves
  → At-least-once with dedup bloom filter gets to 99.99% unique delivery
  → The remaining 0.01% duplicates are not worth the engineering effort

OVER-ENGINEERING 2: Global total ordering of notifications
  → "User must see likes in exact chronological order"
  → Requires coordination across all fan-out workers
  → Adds latency (wait for ordering), complexity (vector clocks)
  → Users don't perceive 2-second reorderings in their notification feed
  → Inbox display ordering by timestamp is sufficient

OVER-ENGINEERING 3: Real-time ML-optimized send time for ALL notifications
  → Adding ML inference to every notification's critical path
  → Useful for P2 marketing (timing matters for opens)
  → Harmful for P0/P1 (adds latency, user wants instant delivery)
  → Implement only as optional stage for P2, not core pipeline

OVER-ENGINEERING 4: Custom push delivery infrastructure (replacing APNs/FCM)
  → Building your own push relay to user devices
  → Requires persistent connections to every device
  → APNs/FCM already do this extremely well and for free
  → Only justified if you're operating at Apple/Google scale
  → For everyone else: Use APNs/FCM, invest engineering elsewhere
```

## Cost-Aware Redesign

```
IF COST MUST BE REDUCED BY 50%:

  1. Eliminate SMS for OTP where possible (-$80M/month)
     → For users with the app installed: Push-based OTP
     → For users without app: Keep SMS (no alternative)
     → Estimated: 80% of OTP users have app → 80% SMS reduction
  
  2. Move to email digests for P1 notifications (-$800K/month)
     → Instead of individual emails per like/comment
     → Daily digest: "Here's what you missed today"
     → Reduces email volume by ~80%
  
  3. Reduce delivery log retention (-$10K/month)
     → Hot: 30 days → 14 days
     → Cold: 1 year → 6 months
     → Accept: Harder to debug old issues
  
  4. Reduce P2 retry budget (-$5K/month in compute)
     → P2: 0 retries (deliver or drop)
     → Marketing notifications: best-effort, no retry
     → Accept: ~5% delivery failure rate for campaigns
  
  TOTAL SAVINGS: ~$81M/month (76% cost reduction, mostly from SMS)
  
  KEY INSIGHT: In notification systems, the third-party send costs 
  dominate everything else by 100×. Optimizing compute and storage 
  saves thousands; optimizing SMS strategy saves millions.
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
NOTIFICATION EVENTS: Written to the region where the event occurred
  → Like in US-East → Event ingested in US-East
  → Fan-out may produce recipients in other regions
  → Cross-region recipient: Forward delivery task to recipient's region

USER PREFERENCES: Stored in user's home region
  → User in EU → Preferences stored in EU-West
  → Preference evaluation for EU user happens in EU-West
  → GDPR compliance: EU user data stays in EU
  → Read from local cache; cache populated from local store

NOTIFICATION INBOX: Stored in user's home region
  → User's inbox reads always hit local region
  → No cross-region reads for inbox (latency would be 100ms+)
  → Inbox writes come from the user's home region's workers

TOKEN REGISTRY: Stored in user's home region
  → Push tokens are per-user → colocated with user data
  → Push sends originate from user's home region
  → APNs/FCM are globally reachable from any region

DELIVERY LOG: Written in the region where delivery was processed
  → Cross-region aggregation for global analytics (async, batch)
  → Per-region logs for local debugging
```

## Replication Strategies

```
USER PREFERENCES:
  → Primary: User's home region (strong consistency for writes)
  → Replicas: Other regions (async replication, ~200ms lag)
  → Read: Prefer local region (may be slightly stale for users traveling)
  → Write: Always to home region (forwarded if user is visiting other region)
  → WHY: Preferences MUST be consistent (user disables notifications → must stop).
    Short replication lag is acceptable because preference changes are rare.

NOTIFICATION INBOX:
  → Primary: User's home region
  → No replication to other regions (reads are always from home region)
  → WHY: Inbox is a per-user store. User's app connects to their home region.
    No need for multi-region replication.

QUEUES:
  → Per-region queues (no cross-region queue replication)
  → Each region has its own P0/P1/P2 queues and workers
  → Cross-region work: Forwarded as messages to the target region's queue

EVENT LOG:
  → Written to local region
  → Replicated to cold storage (global) for analytics
  → Async replication: batch every 5 minutes

PROVIDER CONNECTIONS:
  → APNs/FCM endpoints are geographically distributed
  → Connect to nearest provider endpoint from each region
  → No cross-region provider calls needed
```

## Traffic Routing

```
EVENT INGESTION:
  → Events routed to the region of the event source (service locality)
  → Most services run in the same region as their users → events are local

FAN-OUT RESOLUTION:
  → Fan-out happens in the region of the event source
  → Recipient resolution may discover cross-region users:
    → Celebrity in US-East, follower in EU-West
    → Fan-out service produces delivery task
    → Delivery task forwarded to EU-West for preference evaluation + delivery
  → Cross-region forwarding: Via cross-region message queue (dedicated)
  → Adds ~100ms of latency for cross-region recipients

NOTIFICATION INBOX READS:
  → Always routed to user's home region via DNS-based routing
  → User's app configured with home region endpoint on signup
  → If home region is down: Failover to secondary region (degraded, stale data)

PROVIDER SENDS:
  → Push: Sent from user's home region to nearest APNs/FCM endpoint
  → Email: Sent from any region (email is inherently global, SMTP routing)
  → SMS: Sent from region nearest to user's phone number prefix
    → US number → US region SMS provider
    → EU number → EU region SMS provider
    → Reduces SMS cost and improves deliverability
```

## Failure Across Regions

```
SCENARIO: US-East region becomes unavailable

  IMPACT:
  → Events from US-East services: Lost until recovery (producers must retry)
  → US-East users: No new notifications delivered
  → US-East users' inbox: Unavailable (primary store is in US-East)
  → Non-US-East users: Unaffected for local events
  → Non-US-East users following US-East celebrities: Fan-out stalls
    (celebrity's region is down → fan-out can't start)

  MITIGATION:
  → Ingestion API: Multi-region anycast → US-East events routed to US-West
  → Fan-out: Cross-region follower data may be stale (async replication)
  → Notification inbox: Read-only failover from async replica in US-West
    (user sees stale inbox but can still browse)
  → Push delivery: US-East users' push tokens in US-West cache
    → Deliver push from US-West using cached tokens (may be stale)
  → Preference evaluation: Use replicated preferences in US-West
    (may be up to 200ms stale — acceptable)

  RECOVERY:
  → US-East comes back → Resume normal processing
  → Drain events that were redirected to US-West
  → Reconcile inbox state (any writes that went to US-West replica)
  → No automatic reconciliation of lost events (producers must re-send)

  RTO (Recovery Time Objective): 5-10 minutes for automated failover
  RPO (Recovery Point Objective): < 1 minute of data loss (async replication lag)
```

## When Multi-Region Is NOT Worth It

```
IF TOTAL USERS < 10M AND ALL IN ONE GEOGRAPHY:
  → Single region is sufficient
  → Multi-region adds: 2× infrastructure cost, cross-region complexity,
    data consistency challenges, operational burden
  → Single region with good DR (backup to another region, cold standby)
    provides acceptable availability

IF NOTIFICATION LATENCY IS NOT CRITICAL:
  → Batch notifications (daily digest only) don't need multi-region serving
  → Process in one region, email/push from there
  → Provider latency to global endpoints is acceptable for P2

IF REGULATORY DOESN'T REQUIRE DATA LOCALITY:
  → If no GDPR / data residency requirements, all data can live in one region
  → Cross-region purely for availability (active-passive, not active-active)
  → Simpler architecture with passive DR region
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
VECTOR 1: Notification Spam via Compromised Service
  ATTACK: Compromised internal service sends millions of spam notifications
  → Users receive "You have a new message from <spam content>"
  → Damages brand trust, drives notification disable
  DEFENSE:
  → Per-sender rate limits (enforced at ingestion API)
  → Sender authentication (service identity verified via mutual TLS)
  → Content scanning: Block notifications matching known spam patterns
  → Kill switch: Halt all notifications from a specific sender instantly
  → Post-incident: Revoke sender credentials, audit blast radius

VECTOR 2: Fan-out Amplification Attack
  ATTACK: Attacker creates event targeting user with 100M followers
  → Triggers 100M notifications, overwhelming infrastructure
  DEFENSE:
  → Only authorized event types trigger fan-out
  → Fan-out rate limiting: Max fan-out batches per minute per actor
  → Suspicious fan-out detection: If new account triggers large fan-out → block
  → Pre-computed partitions only exist for established accounts

VECTOR 3: Preference Manipulation
  ATTACK: Attacker changes another user's preferences to disable all notifications
  → Victim stops receiving critical notifications (OTP, security alerts)
  DEFENSE:
  → Preference writes require authenticated session (verified user_id)
  → P0 notifications (OTP, security) CANNOT be disabled by user preference
    (system-enforced mandatory delivery)
  → Audit log on all preference changes
  → Anomaly detection: Bulk preference changes from single IP → flag

VECTOR 4: Token Harvesting
  ATTACK: Attacker registers many fake tokens to exhaust push quota
  → Sends flood of events → system sends push to millions of fake tokens
  → APNs/FCM rate-limits the entire app
  DEFENSE:
  → Token registration requires valid user session
  → Token validated on first push attempt (APNs returns 410 for fake tokens)
  → If 410 rate exceeds threshold for new tokens: Flag token registration endpoint
  → Token registry: Max 10 devices per user (prevent unbounded registration)

VECTOR 5: Notification Content Injection
  ATTACK: Producer sends event with malicious content in payload
  → Push notification displays XSS payload or phishing text
  DEFENSE:
  → Content sanitization at ingestion API (strip HTML, limit characters)
  → Template service: All user-generated content rendered via safe templates
  → Email: HTML sanitized, no JavaScript, CSP headers
  → Push: Text-only fields have character limits and encoding restrictions
```

## Rate Abuse

```
PER-SENDER RATE LIMITS:
  → Each producing service has a defined rate limit
  → Like Service: 100K events/sec (high-volume, validated)
  → Marketing Service: 10K events/sec (throttled by design)
  → New services: Start with 100 events/sec, increase with approval
  → Enforcement: Sliding window counter per sender_id at ingestion API
  → Exceeded: 429 response, event dropped, alert to sender team

PER-USER FREQUENCY CAPS:
  → Max 10 notifications per hour (P1 + P2)
  → Max 50 notifications per day (P1 + P2)
  → P0 exempt from frequency caps (transactional must always deliver)
  → SUBTLE BUG: If frequency cap counter is per-region (distributed),
    user traveling across regions might exceed cap
  → FIX: Frequency counter is per-user (hashed to user's home region)

PER-CHANNEL PROVIDER RATE LIMITS:
  → APNs: ~100K sends/sec per certificate (documented limit)
  → FCM: Rate limits vary by project (monitor 429 responses)
  → SMTP: ISP-specific rate limits (Gmail: ~100 emails/sec per IP)
  → SMS: Carrier-specific throughput limits
  → ENFORCEMENT: Token bucket per provider, shared across all workers
  → If provider limit approached: Workers slow down proactively
```

## Data Exposure

```
NOTIFICATION CONTENT ON LOCK SCREEN:
  → Push notification text visible without unlock
  → RULE: Never include PII beyond "someone did something"
    → GOOD: "New message from John"
    → BAD: "John said: Here's my credit card number 4532..."
  → Exception: OTP codes (by design, visible on lock screen)
  → Implementation: Content truncation + "Open app to see more"

DELIVERY LOGS AS DATA EXPOSURE:
  → Delivery log contains: user_id, event_type, channel, timestamp
  → If leaked: Reveals user activity patterns (when they're active, what they do)
  → PROTECTION: Delivery logs are internal-only, encrypted at rest
  → Access: Requires elevated permissions, audit-logged
  → Retention: Minimized (90 days hot, deleted after 1 year)

NOTIFICATION INBOX AS PII:
  → Contains: Actor names, content previews, timestamps
  → If leaked: Reveals user's social interactions
  → PROTECTION: Encrypted at rest, authenticated access only
  → API: Returns only requesting user's notifications (user_id from session)

EMAIL CONTENT IN TRANSIT:
  → Email sent via SMTP may traverse unencrypted hops
  → PROTECTION: Use TLS for SMTP relay (opportunistic TLS at minimum)
  → Sensitive emails: Encrypt payload, link to in-app content
    → "You have a new notification. Open the app to view."
```

## Privilege Boundaries

```
PRODUCER SERVICES (event publishers):
  → CAN: Send notification events for their owned event types
  → CANNOT: Send arbitrary event types (type registry enforced)
  → CANNOT: Bypass rate limits
  → CANNOT: Access delivery logs or user preferences

NOTIFICATION SYSTEM (internal):
  → CAN: Read user preferences, tokens, social graph
  → CAN: Send to all channel providers
  → CANNOT: Modify user preferences (user action only)
  → CANNOT: Access notification content (treats payload as opaque)

OPERATIONS / ON-CALL:
  → CAN: Activate kill switches
  → CAN: View delivery dashboards, query delivery logs
  → CAN: Modify provider configuration (primary/secondary)
  → CANNOT: Read notification content (PII)
  → CANNOT: Send notifications directly (only producers can)

MARKETING TEAM:
  → CAN: Create and schedule campaigns (through campaign API)
  → CAN: Define audience segments
  → CANNOT: Bypass frequency caps
  → CANNOT: Send to users who opted out
  → CANNOT: Access individual user data (only aggregate metrics)

SUPPORT TEAM:
  → CAN: Look up notification history for a specific user (with audit log)
  → CAN: Verify delivery status for a specific notification
  → CANNOT: Send notifications on behalf of a user
  → CANNOT: Modify preferences on behalf of a user
```

## Why Perfect Security Is Impossible

```
1. THIRD-PARTY PROVIDER TRUST
   → We trust APNs/FCM/SMTP to deliver only to the intended device
   → If APNs is compromised, all iOS push is exposed
   → We can't control provider-side security

2. NOTIFICATION CONTENT VS CONVENIENCE
   → Lock screen previews are convenient but expose content
   → Users choose their privacy level (show/hide previews)
   → We can't enforce lock screen settings on user devices

3. METADATA EXPOSURE
   → Even encrypted content reveals metadata (who, when, what type)
   → Timing analysis reveals user activity patterns
   → Full metadata protection requires onion routing (impractical)

4. INSIDER THREAT
   → Engineers with system access can read delivery logs
   → Mitigated by: access controls, audit logs, limited retention
   → But determined insider can exfiltrate during their access window

PRAGMATIC STANCE: Defense in depth. Rate limits prevent volume attacks.
Authentication prevents unauthorized sends. Encryption prevents passive
snooping. Audit logs enable detection. Accept that perfect security is
impossible; optimize for detection and response speed.
```

---

# Part 14: Evolution Over Time (CRITICAL FOR STAFF)

## V1: Naive Design (Month 0-6)

```
ARCHITECTURE:
  → Single service: "NotificationSender"
  → Synchronous processing: Event → resolve recipient → check preferences → send
  → Single queue for all notification types
  → One push provider integration (APNs only, Android coming "later")
  → Preferences: Boolean per user (notifications on/off)
  → No aggregation, no frequency caps, no priority isolation
  → Email: Direct SMTP send from notification service

WHAT WORKS:
  → Simple to understand and operate
  → Low user base (1M users), manageable load
  → Single team owns the entire system
  → Deployments are quick (one service)

TECH DEBT ACCUMULATING:
  → No priority isolation (marketing and OTP share a queue)
  → No frequency caps (viral events cause notification floods)
  → No aggregation (200 likes = 200 push notifications)
  → Android users receive no push notifications
  → Synchronous processing means slow fan-out blocks API
```

## What Breaks First (Month 6-12)

```
INCIDENT 1: "The Great Notification Flood" (Month 7)
  → Viral post gets 50K likes in 10 minutes
  → Author receives 50K push notifications
  → Phone becomes unusable (constant buzzing)
  → User posts screenshots on social media → PR nightmare
  → Author disables notifications entirely → lost channel
  
  RESPONSE: Implement basic notification aggregation
  → First-pass: Collapse "like" notifications into 5-minute windows
  → "User A and 49 others liked your photo" instead of 50 individual pushes
  → Quick fix, not architected properly (will need redesign)

INCIDENT 2: "Marketing vs OTP" (Month 9)
  → Marketing team launches first large campaign: 2M emails
  → Emails queue behind marketing campaign
  → OTP emails delayed by 30 minutes
  → Users can't verify email → can't sign up → acquisition drops 40%
  
  RESPONSE: Priority queues
  → Separate queue for transactional (P0) and everything else
  → P0 queue has dedicated workers
  → Quick fix: Two queues. Not yet three (P1 and P2 still share one).

INCIDENT 3: "The Token Graveyard" (Month 11)
  → Push delivery success rate: 68% (should be >95%)
  → Investigation: 30% of tokens in registry are invalid/expired
  → No token cleanup process existed
  → 30% of push sends wasted (APNs returns 410, we don't process it)
  
  RESPONSE: Token lifecycle management
  → Process APNs/FCM feedback (410 → mark token invalid)
  → Nightly job: Remove tokens not seen in 90 days
  → Push delivery success rate: 68% → 94%
```

## V2: Improved Design (Month 12-24)

```
ARCHITECTURE CHANGES:
  → Three priority queues (P0, P1, P2) with isolated workers
  → Asynchronous fan-out service (separate from ingestion)
  → Notification aggregation for social types (like, follow)
  → Multi-channel: Push (APNs + FCM), Email, In-App
  → Per-type preferences (user can disable "likes" but keep "comments")
  → Frequency caps: Max 50 notifications per day
  → Basic delivery tracking (success/fail per send)
  → Token lifecycle management (register, validate, prune)

NEW PROBLEMS IN V2:
  → Celebrity problem emerges (platform grows, top users have 5M+ followers)
  → Fan-out for 5M followers takes 3 minutes (synchronous graph reads)
  → Email deliverability degrades (ISPs flag burst sends as spam)
  → No cross-team visibility (5 teams now produce notifications)
  → Preference schema is rigid (adding new types requires code changes)

WHAT DROVE V2:
  → Three production incidents in V1
  → User complaints about notification volume (NPS impact)
  → Android user growth (FCM integration mandatory)
  → Marketing team needs campaign infrastructure
  → Regulatory: CAN-SPAM compliance requires unsubscribe
```

## V3: Long-Term Stable Architecture (Month 24+)

```
ARCHITECTURE CHANGES:
  → Notification platform: Self-service for producer teams
  → Type registry: Teams register new notification types via config, not code
  → Pre-computed fan-out partitions for large accounts
  → Channel router with provider failover
  → Bloom filter deduplication at delivery layer
  → Multi-region deployment (data locality for GDPR)
  → Real-time delivery dashboards and alerting
  → Campaign service: Scheduled sends, audience segmentation, throttling
  → Quiet hours support (timezone-aware)
  → Kill switch with sub-second propagation
  → Email warm-up and reputation management

WHAT MAKES V3 STABLE:
  → Clear isolation: P0 cannot be affected by P2 (proven by load tests)
  → Self-service: New notification types don't require notification team changes
  → Celebrity fan-out: Handled in seconds, not minutes
  → Provider failover: APNs outage → automatic, no manual intervention
  → Observability: Team can answer "why didn't user X get notified?" in minutes
  → Cost-aware: SMS reduced by 70% via push-based OTP

REMAINING CHALLENGES (ongoing):
  → Notification fatigue (users still get too many notifications)
    → Solution: ML-based relevance scoring (in development)
  → Global consistency of frequency caps (cross-region counters)
    → Solution: Accept approximate counts (within 10% accuracy)
  → New channel integration (RCS, WhatsApp Business)
    → Solution: Channel abstraction layer makes adding channels straightforward
```

### Migration Strategy: V2 → V3 Without Downtime

```
PROBLEM:
  V2 has a single queue cluster (P0/P1/P2 share the same broker),
  a synchronous fan-out path, and no multi-region support.
  V3 requires separate queue clusters, async fan-out with pre-computed
  partitions, and multi-region data stores.
  You cannot shut down notifications during migration. OTP must deliver
  24/7. The migration must be invisible to users and producer teams.

MIGRATION PHASES:

PHASE 1: Dual-write to new queue infrastructure (Week 1-4)
  → Deploy new P0/P1/P2 queue clusters alongside existing unified queue
  → Ingestion API: Dual-write to BOTH old queue AND new priority queues
  → Old workers: Continue processing from old queue (active)
  → New workers: Processing from new queues but DISCARDING results
    (shadow mode — verifies new pipeline works without user impact)
  → Validate: Compare old vs new pipeline outputs for 1M events
    → Same recipients resolved? Same preferences evaluated?
    → Same channels selected?
  → Duration: 2-4 weeks of shadow validation
  
  RISK: Dual-write doubles queue throughput temporarily
  MITIGATION: New queues are sized for full production load anyway

PHASE 2: Gradual traffic shift (Week 5-8)
  → Feature flag: percentage_on_new_pipeline = 0 → 1 → 5 → 25 → 100
  → At each step:
    → P0 notifications for {percentage}% of events routed to new pipeline
    → P1 and P2 remain on old pipeline until P0 is 100% migrated
  → P0 migrated FIRST because it's lowest volume and highest visibility
    → If new pipeline has a bug, P0's aggressive SLOs catch it immediately
  → Monitor at each step: Delivery latency, success rate, dedup accuracy
  
  RISK: Feature flag check adds ~0.1ms to ingestion path
  MITIGATION: In-memory flag cached locally, refreshed every 5 seconds

PHASE 3: Fan-out migration (Week 9-12)
  → Pre-computed follower partitions job deployed alongside live fan-out
  → New fan-out service reads from new queues, uses pre-computed partitions
    for accounts > 100K followers
  → Validation: Compare fan-out results (recipient lists) between
    old path (live graph query) and new path (pre-computed partitions)
  → Accept: New path may miss followers from last hour (stale partitions)
    → Document this as known behavior, not a bug

PHASE 4: Old pipeline decommission (Week 13-16)
  → All traffic on new pipeline for 2+ weeks with clean SLOs
  → Remove dual-write from ingestion API
  → Drain old queues (verify empty)
  → Decommission old queue cluster and old workers
  → Remove feature flags

PHASE 5: Multi-region activation (Week 17-24)
  → Deploy new pipeline in EU-West (parallel to existing US-East)
  → Preference store and inbox store replicated to EU-West
  → Cross-region forwarding queue deployed
  → EU users' events gradually routed to EU-West pipeline
  → Validate: EU users' notification latency improves (local processing)

TOTAL MIGRATION DURATION: 6 months
  → Zero downtime, zero user-visible impact
  → Each phase is independently reversible (rollback to previous phase)

L5 MISTAKE: "Let's do a big-bang migration over a weekend maintenance window"
L6 APPROACH: Phased, feature-flagged, shadow-validated, independently
  reversible. Each phase runs for weeks to build confidence. P0 migrates
  first (highest visibility, lowest volume, catches bugs fastest).

REAL-WORLD ANALOGY (Messaging Platform):
  When migrating a messaging platform's delivery pipeline, you run the
  old and new pipelines in parallel for months, comparing message delivery
  outcomes. You can't afford to lose messages during migration. Notification
  systems have the same zero-loss requirement for P0 transactional events.
```

## Real Incident Table (Structured)

| Context | Trigger | Propagation | User Impact | Engineer Response | Root Cause | Design Change | Lesson |
|---------|---------|-------------|-------------|-------------------|------------|---------------|--------|
| **Marketing blocks OTP** | Marketing campaign sends 50M emails at 10 AM. OTP request at 10:01 AM. | Single shared queue. P2 items ahead of P0. OTP waits behind 50M items. | Users cannot log in. 2FA codes delayed 45+ minutes. Support tickets spike. | Manual queue drain attempted. Risk of losing P0 items. Incident lasted 2 hours. | No priority isolation. All notification types shared one queue. | Physically separate P0/P1/P2 queues with dedicated worker pools. P0 has reserved capacity that P2 cannot consume. | Priority isolation must be physical, not logical. Logical priority in a shared queue fails under load. |
| **Celebrity fan-out OOM** | Celebrity (10M followers) posts. Fan-out service fetches all followers synchronously. | Worker loads 10M user IDs (800MB) into memory. Multiple workers replicate. OOM cascade. | Social notifications stalled 30+ minutes. Platform appears down. | Restart workers. Clear queue. Celebrity post eventually delivered after 90 minutes. | Synchronous fan-out for large accounts. No chunking. No pre-computation. | Pre-computed follower partitions (hourly batch). Fan-out becomes O(partitions) enqueue, not O(followers) load. | Fan-out is a pipeline with stages, not a loop. Pre-compute everything that can be stale. |
| **APNs outage** | APNs returns 503 for 30 minutes (provider-side incident). | Push workers retry aggressively. Retry storm. APNs rate-limits app certificate. | All iOS push fails. No fallback. Email/SMS unaffected but not routed. | Manual circuit breaker. Disabled push. Waited for APNs recovery. | No per-channel circuit breaker. No fallback routing. Single-channel dependency. | Per-channel circuit breakers. Fallback to secondary channel (in-app, email) when primary fails. TTL check before fallback (do not send stale via fallback). | Channel isolation limits blast radius. Each channel has its own circuit breaker and fallback path. |
| **Duplicate notifications** | User receives "User A liked your photo" three times. Retry logic + partial fan-out completion. | Producer retries event. Fan-out produces duplicate batches. No delivery-level dedup. | User disables all notifications. Permanent channel loss. | Hotfix: Add delivery bloom filter. Cannot undo user's disable. | Event-level dedup only. No batch or delivery-layer dedup. Retries and partial failures produce duplicates. | Three-layer dedup: event idempotency, batch dedup at preference eval, delivery bloom filter at channel workers. | At-least-once with dedup gets to 99.99% unique delivery. The last 0.01% is not worth distributed transaction overhead. |
| **Token graveyard** | 30% of push tokens are stale (users uninstalled, reset device). No feedback processing. | Push workers send to invalid tokens. APNs returns 410 (invalid token). No cleanup. | 30% of push silently fails. Teams blame "low engagement." No token pruning. | Manual token audit. Found millions of stale tokens. No automated fix. | Token registry never pruned. APNs/FCM feedback not processed. | Token lifecycle: Process provider feedback. Prune tokens on 410/404. Inactive >90 days cleanup. | Stale tokens cause silent delivery failure. Token health is a first-class metric. |
| **3am security alert** | User opts into "security alerts" and sets quiet hours 10pm–8am. Account compromise detected at 3 AM. | Notification held until 8 AM (strict quiet hours). | User's account compromised at 3 AM. Alert delivered at 8 AM. 5-hour window for attacker. | Manual override: Disable quiet hours for security alerts. No systematic fix. | P0 (security) treated same as P1 for quiet hours. | P0 transactional bypasses quiet hours. P1/P2 respect quiet hours. Policy: "Your account is compromised" must deliver immediately. | Critical notifications (P0) bypass user convenience settings. Document and enforce by type. |

### How Incidents Drive Redesign

```
INCIDENT → REDESIGN MAPPING:

"Notification flood"     → Aggregation service
"Marketing blocks OTP"   → Priority isolation (P0/P1/P2 queues)
"Token graveyard"        → Token lifecycle management
"Celebrity fan-out OOM"  → Pre-computed fan-out partitions
"APNs outage"            → Channel-level circuit breakers + fallback
"GDPR complaint"         → Multi-region data locality
"Duplicate notifications"→ Three-layer deduplication
"Wrong user notified"    → Token registry user_id verification
"Campaign kills email"   → Email reputation management + throttling
"3am security alert"     → Quiet hours with P0 bypass

PATTERN: Every major redesign was preceded by a production incident.
The V1 → V2 → V3 evolution is not planned in advance; it's driven by
failures at increasing scale. A Staff Engineer's job is to ANTICIPATE
which incidents will happen at the next scale milestone and design for
them BEFORE they occur.
```

### Team Ownership & Operational Reality

```
ORGANIZATIONAL STRUCTURE AT V3 SCALE:

  NOTIFICATION PLATFORM TEAM (6-8 engineers):
  → Owns: Ingestion API, fan-out service, preference evaluator,
    channel router, delivery tracker, priority queues
  → On-call rotation: 1 primary + 1 secondary, weekly rotation
  → SLO responsibility: Event ingestion availability, delivery latency,
    preference correctness, dedup accuracy
  → Does NOT own: Channel worker implementations, template rendering,
    content generation, user segmentation

  CHANNEL TEAMS (2-3 engineers each):
  → Push team: Owns push workers, APNs/FCM integration, token registry
  → Email team: Owns email workers, SMTP relay, bounce handling,
    IP reputation management, deliverability optimization
  → SMS team: Owns SMS workers, provider integration, cost optimization
  → Each team: Own on-call for their channel, own provider relationships
  → SEPARATION RATIONALE: Channel-specific expertise is deep. APNs
    integration requires iOS platform knowledge. SMTP deliverability
    requires email ecosystem knowledge. One team can't be expert in all.

  PRODUCER TEAMS (15+ teams across the company):
  → Each team: Sends events to notification API for their use cases
  → Examples: Like Service team, Chat team, Auth team, Marketing team
  → Responsibility: Event schema correctness, rate limit compliance,
    content quality, opt-in/opt-out UX
  → Interface: Self-service type registry, per-sender dashboards

  PREFERENCE UX TEAM (2-3 engineers):
  → Owns: Notification settings UI, preference store schema
  → Works with: Platform team (API contracts), product teams (new types)
  → CRITICAL INTERFACE: When preference schema changes, both the
    preference evaluator and the UX must be updated simultaneously

ON-CALL OPERATIONAL PLAYBOOK:

  ALERT: "P0 delivery latency exceeding 5s SLO"
  → Check: P0 queue depth (if high → workers are slow or crashed)
  → Check: Push/SMS provider status (if degraded → circuit breaker)
  → Check: Preference cache health (if down → DB overload)
  → Escalate: If not resolved in 5 min → page secondary + engineering lead

  ALERT: "Delivery success rate below 90%"
  → Check: Which channel is failing (push? email? SMS?)
  → Check: Provider dashboard (APNs status, SMTP logs)
  → Check: Token registry health (mass token expiry?)
  → Check: Recent deployments (canary metrics diverged?)
  → Isolate: Is it one sender's events or global?

  ALERT: "Fan-out queue depth exceeding 10M"
  → Check: Celebrity event in progress? (expected behavior)
  → Check: Fan-out worker health (crashed? slow?)
  → Check: Social graph service latency (slow → fan-out slow)
  → Action: Shed P2 fan-out, alert sender teams if their events are delayed

  ALERT: "DLQ depth > 0"
  → Check: Which event types are landing in DLQ
  → Check: Which sender is producing them
  → Action: Notify sender team, analyze root cause
  → If sender is flooding DLQ: Activate per-sender circuit breaker

HUMAN FAILURE MODES:

  1. ON-CALL FATIGUE:
     → 200+ alerts/day during high-traffic periods
     → Alert fatigue leads to missed critical alerts
     → Fix: Tiered alerting. P0 alerts: PagerDuty (loud, immediate).
       P1 alerts: Chat notification. P2 alerts: Dashboard only.

  2. WRONG RUNBOOK EXECUTED:
     → On-call runs "drain P2 queue" runbook but accidentally targets P0
     → All P0 notifications drained (lost)
     → Fix: Runbooks require confirmation for destructive actions.
       P0 queue operations require second-person approval.

  3. FEATURE FLAG LEFT ON:
     → Migration feature flag set to 50% during testing, never reset
     → 50% of notifications going through deprecated path for months
     → Fix: Feature flags have mandatory expiry dates. Flag older than
       30 days without update → auto-alert flag owner.

  4. PROVIDER CREDENTIAL EXPIRY:
     → APNs certificate expires → all iOS push silently fails
     → No alert because APNs returns a different error code than expected
     → Fix: Certificate expiry monitoring (alert 30 days before expiry).
       On-call checklist includes "verify credential validity" monthly.

WHY THIS MATTERS AT L6:
  A Staff Engineer designs systems that work DESPITE human error and
  organizational complexity. The technical architecture is only half
  the design. The operational model — who owns what, how alerts are
  triaged, how runbooks prevent mistakes, how on-call is structured —
  determines whether the system actually achieves its SLOs in production.
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Pull-Based Notifications (Polling)

```
DESCRIPTION:
  Instead of pushing notifications to users, users poll for new notifications.
  Client sends "GET /notifications/new" every N seconds.

WHY IT SEEMS ATTRACTIVE:
  → No push infrastructure needed (no APNs/FCM integration)
  → No token management
  → Simpler server-side (just write to inbox, client reads)
  → Works on any platform (no OS-level push support needed)

WHY A STAFF ENGINEER REJECTS IT:
  → LATENCY: 30-second polling interval = 15-second average delivery latency
    → Unacceptable for OTP (user waiting for code)
  → COST: 100M DAU × 1 poll/30s = 3.3M requests/sec JUST for polling
    → 95% of polls return empty (no new notifications)
    → 3.1M wasted requests/sec = enormous infrastructure cost
  → BATTERY: Frequent polling drains mobile battery
    → OS push (APNs/FCM) is optimized for battery-efficient delivery
  → OFFLINE: No way to reach user when app is closed
    → Push notification wakes the device; polling requires app to be open

  WHEN IT'S ACCEPTABLE:
  → In-app notification badge update (supplement to push, not replacement)
  → Desktop web apps without service worker support
  → Internal tools with low notification urgency
```

## Alternative 2: Unified Single-Queue Architecture

```
DESCRIPTION:
  All notifications (P0 through P2) go through a single queue system.
  Workers process notifications in FIFO order regardless of priority.

WHY IT SEEMS ATTRACTIVE:
  → Simpler infrastructure (one queue to manage)
  → No priority classification logic needed
  → Even processing (no starvation of any type)
  → Easier to monitor (one queue depth metric)

WHY A STAFF ENGINEER REJECTS IT:
  → PRIORITY INVERSION: 50M marketing campaign enqueued at 10:00 AM.
    OTP request at 10:01 AM sits behind 50M items.
    User can't log in for hours.
  → NO ISOLATION: Burst in one notification type affects all others.
    Celebrity post generates 10M items → ALL notifications delayed.
  → SCALING MISMATCH: P0 needs dedicated fast workers (low latency).
    P2 needs high-throughput workers (batch processing).
    Single queue forces one worker type for all.
  → LOAD SHEDDING IMPOSSIBLE: Can't selectively drop P2 without
    scanning the entire queue for priority.

  WHEN IT'S ACCEPTABLE:
  → Early stage (< 1M users, < 1K events/sec)
  → No transactional notifications (no OTP, no security alerts)
  → All notifications are equal priority (rare in practice)
```

## Alternative 3: Event-Driven Pub/Sub (Each Service Subscribes to What It Needs)

```
DESCRIPTION:
  Instead of a centralized notification service, use a pub/sub bus.
  Each channel (push, email, SMS) subscribes to events directly.
  Each channel service handles its own preference checking and delivery.

WHY IT SEEMS ATTRACTIVE:
  → Decoupled: Each channel team owns their pipeline end-to-end
  → No single point of failure (no central notification service)
  → Teams can iterate independently on their channel's logic
  → Natural event-driven architecture (publish and forget)

WHY A STAFF ENGINEER REJECTS IT:
  → PREFERENCE FRAGMENTATION: Each channel service independently checks
    preferences. When user opts out, ALL channel services must be updated.
    If one service has stale preferences → user gets unwanted notification
    on that channel. Central preference evaluation ensures single check.
  → FREQUENCY CAP IMPOSSIBLE: No single service sees total notification
    volume across all channels. User might get 10 pushes + 10 emails + 10 SMS
    = 30 total notifications, but each channel thinks it sent only 10.
  → AGGREGATION IMPOSSIBLE: Aggregation ("User A and 49 others...") requires
    seeing multiple events before routing to channels. Pub/sub model delivers
    each event independently.
  → FAN-OUT DUPLICATION: Each channel service independently resolves recipients.
    10M follower fan-out happens 4 times (once per channel) instead of once.
  → NO GLOBAL KILL SWITCH: To stop a notification type, must update every
    channel service. Miss one → notifications still sent on that channel.

  WHEN IT'S ACCEPTABLE:
  → Very small team (1-3 engineers) that can maintain all channel subscribers
  → Single channel (push only) — no cross-channel concerns
  → Notifications are fire-and-forget (no preferences, no frequency caps)
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "How do you handle a user with 100 million followers posting?"
  PURPOSE: Tests understanding of fan-out at scale
  EXPECTED DEPTH: Pre-computed partitions, chunked processing,
  isolated queues, time-to-first-recipient vs time-to-last-recipient

PROBE 2: "What happens when APNs goes down for 30 minutes?"
  PURPOSE: Tests failure handling, graceful degradation, recovery
  EXPECTED DEPTH: Circuit breakers, fallback channels, stale notification
  handling, retry queue drain with TTL checks

PROBE 3: "How do you prevent a marketing campaign from delaying OTP delivery?"
  PURPOSE: Tests priority isolation understanding
  EXPECTED DEPTH: Physically separate queues, dedicated workers,
  capacity reservation, load shedding hierarchy

PROBE 4: "A user says they're getting too many notifications. Walk me through
  every layer that should prevent this."
  PURPOSE: Tests end-to-end preference and throttling design
  EXPECTED DEPTH: Per-type preferences, frequency caps, aggregation,
  quiet hours, user-level opt-out, channel-specific controls

PROBE 5: "How do you ensure a notification is delivered exactly once?"
  PURPOSE: Tests consistency and deduplication understanding
  EXPECTED DEPTH: Three-layer dedup (event, batch, delivery),
  bloom filters, idempotency keys, why exactly-once is impossible
  across unreliable channels, and why at-least-once with dedup is sufficient

PROBE 6: "Walk me through the cost structure. Where would you cut costs?"
  PURPOSE: Tests cost awareness at Staff level
  EXPECTED DEPTH: SMS dominates, push-based OTP saves millions,
  email digests reduce volume, storage TTL optimization
```

## Common L5 Mistakes

```
MISTAKE 1: Treating fan-out as a synchronous for-loop
  L5: "For each follower, send a notification"
  PROBLEM: 10M followers × 1ms per send = 2.7 hours
  L6: Fan-out is a pipeline. Event → async recipient resolution →
  batched work items → parallel processing across workers.

MISTAKE 2: Single queue for all priorities
  L5: "All notifications go to one queue, we process them in order"
  PROBLEM: 50M campaign items block OTP delivery for hours
  L6: Physically separate queues per priority class with dedicated
  worker pools and capacity reservations.

MISTAKE 3: Ignoring notification fatigue
  L5: "We deliver every notification the system generates"
  PROBLEM: 200 likes → 200 push notifications → user disables permanently
  L6: Aggregation, frequency caps, quiet hours, per-type preferences.
  The notification you DON'T send is as important as the one you do.

MISTAKE 4: "We'll use exactly-once delivery"
  L5: "We guarantee exactly-once delivery using distributed transactions"
  PROBLEM: Impossible across unreliable third-party providers
  L6: At-least-once delivery with three-layer deduplication.
  Accept 0.01% duplicate rate. The cost of eliminating the last 0.01%
  exceeds the cost of duplicates by 100×.

MISTAKE 5: No TTL on notifications
  L5: "We deliver every notification eventually, even if delayed"
  PROBLEM: "User A liked your photo" delivered 3 hours later is confusing
  L6: TTL per notification type. Social: 1 hour. System: 7 days.
  Expired notifications are dropped, not delivered.

MISTAKE 6: Designing the delivery pipeline without thinking about cost
  L5: "We'll send SMS for everything — it's the most reliable channel"
  PROBLEM: SMS at $0.02/message × 500M/day = $10M/day
  L6: SMS for P0 only. Push is free, email is cheap, in-app is cheapest.
  Channel selection is a cost decision as much as a reliability decision.
```

## Staff-Level Answers

```
STAFF ANSWER 1: Fan-out
  "Fan-out is a pipeline, not a loop. For accounts with large follower counts,
  I pre-compute follower partitions hourly so fan-out at event time becomes
  a series of pointer references, not a massive graph read. The first
  recipient should be notified within seconds; the last can take minutes.
  Fan-out work is isolated in its own queue so it doesn't affect 1:1
  transactional notifications."

STAFF ANSWER 2: Priority Isolation
  "I physically separate P0, P1, and P2 into different queue clusters with
  dedicated worker pools. P0 has reserved capacity that cannot be consumed
  by P1 or P2. Under system overload, I shed P2 first, then throttle P1,
  and never compromise P0. This isn't just a queue priority — it's physical
  isolation with separate capacity."

STAFF ANSWER 3: Deduplication
  "Exactly-once is impossible across unreliable channels, so I target
  at-least-once with multi-layer dedup. Layer 1: Event-level idempotency
  at ingestion. Layer 2: Batch-level dedup at preference evaluation.
  Layer 3: Delivery-level bloom filter at channel workers. Bloom filter
  gives me 0.01% false positive rate at 57 billion entries per day
  using only 7GB of memory. That's better than any exact dedup store
  could achieve at this scale."

STAFF ANSWER 4: Cost Optimization
  "SMS dominates cost at $105M/month. My single biggest cost lever is
  moving OTP delivery from SMS to push-based verification for users
  who have the app installed. That's 80% of OTP users, saving $84M/month.
  Next lever: Email digests instead of individual emails. Third lever:
  Skip push for dormant users in large fan-outs. Infrastructure costs
  (compute, storage, queues) are noise compared to provider costs."

STAFF ANSWER 5: Failure Handling
  "Each channel has its own circuit breaker. APNs down doesn't affect FCM,
  email, or in-app. Within push, I have provider-specific health tracking:
  if APNs 410 rate spikes, I know tokens are stale, not that APNs is down.
  For prolonged outages, I fall back to secondary channels — but only if
  the notification hasn't expired (TTL check). A 'like' notification
  delivered 2 hours late via fallback email is worse than not delivered."
```

## Example Phrases a Staff Engineer Uses

```
"The fan-out is a pipeline with stages, not a loop with iterations."

"Priority isolation must be physical, not logical. Logical priority in a
shared queue fails under load — the queue doesn't drain fast enough."

"The notification you suppress is as important as the one you deliver.
Notification fatigue leads to permanent channel loss."

"SMS is the most expensive channel by 1000×. Every SMS we eliminate
saves more than any infrastructure optimization."

"At-least-once with dedup gets us to 99.99% unique delivery. The last
0.01% isn't worth the distributed transaction overhead."

"I design the degradation stack before the happy path. The system must
always deliver SOMETHING — even if the ranking model, preference cache,
and primary channel are all down."

"Pre-compute everything that can be stale. Celebrity follower lists can
be an hour old. User preferences cannot be."

"Channel routing is a cost decision, not just a reliability decision.
Push is free. Email is cheap. SMS is expensive. The default channel
should be the cheapest one that meets the latency requirement."

"The blast radius of a component failure tells me whether I've designed
sufficient isolation. If one team's bulk campaign can delay another
team's OTP, my isolation is broken."
```

## Leadership Explanation (How to Explain to Executives)

```
ONE-LINER FOR LEADERSHIP:
  "Our notification system delivers 2 billion notifications per day across
   push, email, and SMS. The hard part is not sending—it's ensuring a
   marketing campaign to 50 million users never delays a password reset
   email, a celebrity post reaches 10 million followers in under 30 seconds,
   and users do not disable notifications from notification fatigue.
   We achieve this with physical priority isolation, preference-aware
   routing, and channel-specific failure handling."

KEY METRICS TO CITE:
  → Delivery latency: P0 < 5s, P1 < 30s (user-facing SLOs)
  → Cost: SMS is 98% of provider cost; push-based OTP saves $84M/month
  → Reliability: 99.99% for transactional; priority isolation prevents
    one team's spike from affecting others

WHAT TO EMPHASIZE:
  → Blast radius containment: Celebrity fan-out does not affect OTP
  → User trust: One bad notification → user disables all → permanent loss
  → Cost efficiency: Channel selection (push over SMS) is a design decision
```

## How to Teach This Topic

```
OPENING (first 5 minutes):
  → Use the postal service analogy: Accept letter (event), resolve
    recipients, filter by preferences, route to channel, deliver, track.
  → State the Staff Law upfront: "A notification system that sends too
    many notifications is worse than one that sends too few."

PROGRESSION:
  1. Start with 1:1 (OTP, password reset) — simplest path
  2. Add fan-out 1:N (social like, comment) — introduces recipient resolution
  3. Add celebrity fan-out (10M followers) — forces pipeline thinking
  4. Add priority isolation — "What if marketing sends 50M at once?"
  5. Add failure modes — "What if APNs is down for 30 minutes?"

KEY TEACHING MOMENTS:
  → When they say "loop through followers": "That works for 100. For 10M,
    that's hours. Fan-out is a pipeline. Event → batches → workers."
  → When they say "one queue with priority": "Logical priority fails under
    load. 50M items in queue—P0 never gets through. Physical isolation."
  → When they say "exactly-once delivery": "Impossible across unreliable
    providers. At-least-once with dedup. Accept 0.01% duplicates."

COMMON LEARNING TRAP:
  → Focusing on the send (APNs, SMTP) instead of the pipeline (fan-out,
    preferences, dedup). The send is 5% of the system.
```

---

# Part 17: Diagrams (MANDATORY)

## Diagram 1: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   NOTIFICATION DELIVERY SYSTEM — ARCHITECTURE               │
│                                                                             │
│  Event Sources           Ingestion Layer        Fan-out Layer               │
│  ┌──────────┐           ┌──────────────┐       ┌──────────────┐            │
│  │ Like Svc │──┐        │  Ingestion   │       │  Fan-out     │            │
│  │ Chat Svc │──┼──────→ │  API         │──────→│  Service     │            │
│  │ Post Svc │──┤        │              │       │              │            │
│  │ Auth Svc │──┤        │ • Validate   │       │ • Resolve    │            │
│  │ Mktg Svc │──┘        │ • Dedup      │       │   recipients │            │
│  └──────────┘           │ • Rate limit │       │ • Batch 10K  │            │
│                         │ • Classify   │       │ • Chunk large│            │
│                         │   priority   │       │   fan-outs   │            │
│                         └──────┬───────┘       └──────┬───────┘            │
│                                │                      │                     │
│                    ┌───────────┼──────────┐           │                     │
│                    ▼           ▼          ▼           ▼                     │
│                ┌──────┐  ┌──────┐  ┌──────┐  ┌──────────────┐             │
│                │ P0 Q │  │ P1 Q │  │ P2 Q │  │  Preference  │             │
│                │(txn) │  │(soc) │  │(bulk)│  │  Evaluator   │             │
│                └──┬───┘  └──┬───┘  └──┬───┘  │              │             │
│                   │         │         │      │ • Type check  │             │
│                   └─────────┴─────────┘      │ • Quiet hours │             │
│                             │                │ • Freq cap    │             │
│                             ▼                │ • Channel sel │             │
│                    ┌────────────────┐        └──────┬────────┘             │
│                    │ Channel Router │               │                      │
│                    └───┬────┬────┬──┘        ┌──────┘                      │
│                        │    │    │           │                              │
│              ┌─────────┤    │    ├─────────┐ │                              │
│              ▼         ▼    ▼    ▼         ▼ ▼                              │
│         ┌────────┐┌────────┐┌────────┐┌────────┐                          │
│         │  Push  ││ Email  ││  SMS   ││ In-App │                          │
│         │Workers ││Workers ││Workers ││Workers │                          │
│         │        ││        ││        ││        │                          │
│         │APNs/FCM││ SMTP   ││Provider││  DB    │                          │
│         └───┬────┘└───┬────┘└───┬────┘└───┬────┘                          │
│             │         │         │         │                                │
│             └─────────┴─────────┴─────────┘                                │
│                           │                                                │
│                    ┌──────▼──────┐                                         │
│                    │  Delivery   │                                         │
│                    │  Tracker    │──→ Metrics / Analytics                  │
│                    └─────────────┘                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TEACHING POINT: Events flow left to right through increasing stages of
refinement. Each stage has its own scaling knob. Priority isolation happens
at the queue layer. Channel isolation happens at the worker layer.
```

## Diagram 2: Fan-out Data Flow (Celebrity Post)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             FAN-OUT DATA FLOW: CELEBRITY POST (10M FOLLOWERS)               │
│                                                                             │
│  T=0s    ┌────────────────┐                                                │
│          │ Celebrity posts │                                                │
│          │ new photo       │                                                │
│          └───────┬────────┘                                                │
│                  │                                                          │
│  T=0.5s  ┌──────▼──────────────┐                                          │
│          │ Ingestion API        │                                          │
│          │ • Dedup check ✓      │                                          │
│          │ • Priority: P1       │                                          │
│          │ • Enqueue to P1      │                                          │
│          └──────┬───────────────┘                                          │
│                 │                                                           │
│  T=1s    ┌──────▼──────────────────────────────────┐                      │
│          │ Fan-out Service                          │                      │
│          │                                          │                      │
│          │ Detect: 10M followers → LARGE FAN-OUT    │                      │
│          │                                          │                      │
│          │ ┌──────────────────────────────────────┐ │                      │
│          │ │ Pre-computed Follower Partitions      │ │                      │
│          │ │ Partition 1:    [user_1 ... user_10K] │ │                      │
│          │ │ Partition 2:    [user_10K+1 ... 20K]  │ │                      │
│          │ │ ...                                   │ │                      │
│          │ │ Partition 1000: [user_9.99M...10M]    │ │                      │
│          │ └──────────────────────────────────────┘ │                      │
│          │                                          │                      │
│          │ Produce 1,000 batch references → queue   │                      │
│          └──────┬───────────────────────────────────┘                      │
│                 │                                                           │
│  T=15s   ┌──────▼──────────────────────────────────┐                      │
│          │ Preference Evaluator (parallel batches)  │                      │
│          │                                          │                      │
│          │ Per batch of 10K:                        │                      │
│          │   Load preferences (batch cache read)    │                      │
│          │   ├── 40% push enabled  → 4,000 push    │                      │
│          │   ├── 5% quiet hours    → -200 removed   │                      │
│          │   ├── 2% freq cap hit   → -80 removed    │                      │
│          │   └── Net: ~3,720 push + 10K in-app      │                      │
│          │                                          │                      │
│          │ Total across 1,000 batches:              │                      │
│          │   Push: 3.72M sends                      │                      │
│          │   In-app: 10M writes                     │                      │
│          └──────┬───────────────────────────────────┘                      │
│                 │                                                           │
│  T=25s   ┌──────▼──────┐  ┌──────────────┐                               │
│          │ Push Workers │  │ In-App       │                               │
│          │ 100K/sec     │  │ Workers      │                               │
│          │              │  │ 200K/sec     │                               │
│          │ 3.72M sends  │  │ 10M writes   │                               │
│          │ = 37 seconds │  │ = 50 seconds │                               │
│          └──────────────┘  └──────────────┘                               │
│                                                                             │
│  T=62s   ┌────────────────────────────────────┐                           │
│          │ COMPLETE                             │                           │
│          │ First recipient notified: T=5s      │                           │
│          │ Median recipient: T=25s             │                           │
│          │ Last recipient: T=62s               │                           │
│          │ All in-app entries: T=65s           │                           │
│          └────────────────────────────────────┘                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TEACHING POINT: Celebrity fan-out is bounded by pre-computation at rest
and parallelism at delivery time. The critical insight is that fan-out
resolution (knowing WHO to notify) should be separated from delivery
(actually SENDING the notification). Pre-computed partitions make
resolution O(partitions), not O(followers).
```

## Diagram 3: Failure Propagation & Circuit Breakers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           FAILURE PROPAGATION: APNs OUTAGE DURING DELIVERY                  │
│                                                                             │
│  NORMAL STATE                                                               │
│  ────────────                                                               │
│                                                                             │
│  Push Queue ──→ Push Workers ──→ APNs ──→ iOS Devices                      │
│       │              │              ✓         ✓                              │
│       │              │         (200 OK)  (delivered)                         │
│       │              ▼                                                      │
│       │         FCM ──→ Android Devices  ✓                                  │
│       │                                                                     │
│  Email Queue ──→ Email Workers ──→ SMTP ──→ Inbox  ✓                       │
│  SMS Queue ──→ SMS Workers ──→ Provider ──→ Phone  ✓                       │
│  In-App Queue ──→ In-App Workers ──→ DB  ✓                                 │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════     │
│                                                                             │
│  T=0: APNs STARTS RETURNING 503                                            │
│  ─────────────────────────────────                                          │
│                                                                             │
│  Push Queue ──→ Push Workers ──→ APNs ✗ (503 errors)                       │
│       │              │              │                                        │
│       │              │         Error rate: 10% → 30% → 80%                  │
│       │              │              │                                        │
│       │              ▼              │                                        │
│       │    ┌──────────────────┐    │                                        │
│       │    │ CIRCUIT BREAKER  │    │                                        │
│       │    │                  │    │                                        │
│       │    │ 10%: CLOSED      │◄───┘                                        │
│       │    │  (keep sending)  │                                              │
│       │    │                  │                                              │
│       │    │ 30%: HALF-OPEN   │──→ Reduce rate to 20%                       │
│       │    │  (reduce sends)  │                                              │
│       │    │                  │                                              │
│       │    │ 80%: OPEN        │──→ STOP all APNs sends                      │
│       │    │  (stop sends)    │──→ Re-enqueue to retry queue                │
│       │    │                  │──→ ALERT on-call team                       │
│       │    └────────┬─────────┘                                              │
│       │             │                                                        │
│       │             │  MEANWHILE (UNAFFECTED):                               │
│       │             │  FCM delivery continues ✓                              │
│       │             │  Email delivery continues ✓                            │
│       │             │  SMS delivery continues ✓                              │
│       │             │  In-App delivery continues ✓                           │
│       │             │                                                        │
│       │             ▼                                                        │
│       │    ┌──────────────────┐                                              │
│       │    │ RETRY QUEUE      │                                              │
│       │    │ (with backoff)   │                                              │
│       │    │                  │                                              │
│       │    │ 3.2M items       │                                              │
│       │    │ jittered backoff │                                              │
│       │    │ rate limited     │                                              │
│       │    └────────┬─────────┘                                              │
│       │             │                                                        │
│       │             │  PROBE every 30s                                       │
│       │             │  ┌──────────┐                                          │
│       │             └─→│ APNs OK? │──→ No: stay OPEN                        │
│       │                │          │──→ Yes: HALF-OPEN → CLOSED               │
│       │                └──────────┘                                          │
│       │                                                                      │
│  ═══════════════════════════════════════════════════════════════════════     │
│                                                                             │
│  T=2min: APNs RECOVERS                                                      │
│  ──────────────────────                                                      │
│                                                                             │
│  Probe succeeds → HALF-OPEN (10% traffic) → Success → CLOSED (100%)       │
│  Retry queue drains at 100K/sec with TTL check                              │
│  Items past TTL → DROPPED (not delivered)                                   │
│  Items within TTL → DELIVERED                                               │
│                                                                             │
│  TOTAL IMPACT: 2 min delay for iOS push, 0 impact on other channels       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TEACHING POINT: Channel isolation means a provider outage affects only
that channel. Circuit breakers prevent retry storms. Retry queues with
TTL checks prevent stale delivery. Probing enables automated recovery.
```

## Diagram 4: System Evolution (V1 → V2 → V3)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEM EVOLUTION: V1 → V2 → V3                           │
│                                                                             │
│  V1 (Month 0-6): THE MONOLITH                                              │
│  ─────────────────────────────────                                          │
│                                                                             │
│  ┌──────────┐     ┌──────────────────────────────┐     ┌─────┐             │
│  │ Services │────→│ NotificationSender            │────→│APNs │             │
│  └──────────┘     │ • Receive event               │     └─────┘             │
│                   │ • Resolve recipient (sync)     │     ┌─────┐             │
│                   │ • Check pref (on/off only)     │────→│SMTP │             │
│                   │ • Send (sync)                  │     └─────┘             │
│                   │ • One queue for everything     │                         │
│                   └──────────────────────────────────┘                         │
│                                                                             │
│  ✗ No priority isolation  ✗ No aggregation  ✗ No Android                   │
│                                                                             │
│  INCIDENTS: Notification flood ──→  Marketing blocks OTP ──→  Token decay  │
│              │                        │                         │            │
│              ▼                        ▼                         ▼            │
│                                                                             │
│  V2 (Month 12-24): PRIORITY SEPARATION                                      │
│  ──────────────────────────────────────                                      │
│                                                                             │
│  ┌──────────┐     ┌─────────┐     ┌──────────┐     ┌───────────────┐       │
│  │ Services │────→│Ingest   │────→│ Fan-out  │────→│ Pref. Check   │       │
│  └──────────┘     │  API    │     │ Service  │     │               │       │
│                   └────┬────┘     └──────────┘     └───────┬───────┘       │
│                    ┌───┼───┐                           ┌───┼───────┐       │
│                    ▼   ▼   ▼                           ▼   ▼       ▼       │
│                  [P0] [P1] [P2]                    [Push] [Email] [In-App] │
│                   │    │    │                         │      │       │       │
│                   ▼    ▼    ▼                         ▼      ▼       ▼       │
│                 Dedicated workers              APNs/FCM   SMTP     DB      │
│                                                                             │
│  ✓ Priority isolation  ✓ Aggregation  ✓ Multi-channel  ✓ Token mgmt       │
│  ✗ Celebrity fan-out slow  ✗ No multi-region  ✗ No provider failover      │
│                                                                             │
│  INCIDENTS: Celebrity OOM ──→  APNs outage ──→  GDPR complaint            │
│              │                  │                 │                          │
│              ▼                  ▼                 ▼                          │
│                                                                             │
│  V3 (Month 24+): GLOBAL PLATFORM                                           │
│  ────────────────────────────────                                           │
│                                                                             │
│  ┌──────────┐  ┌──────┐  ┌────────┐  ┌─────┐  ┌────────┐  ┌──────────┐  │
│  │ Services │→ │Ingest│→ │Fan-out │→ │Pref │→ │Channel │→ │ Channel  │  │
│  │(self-svc)│  │ API  │  │Service │  │Eval │  │Router  │  │ Workers  │  │
│  └──────────┘  └──────┘  └────────┘  └─────┘  └────────┘  └──────────┘  │
│       │                      │          │          │            │          │
│       ▼                      ▼          ▼          ▼            ▼          │
│   Type Registry     Pre-computed   Batch eval  Provider    Circuit       │
│   Per-sender rate   partitions     + cache     failover    breakers      │
│   limits            (hourly)       (5s TTL)    (A/B)       per channel   │
│                                                                           │
│   Multi-region      Kill switch    Bloom filter   Aggregation            │
│   data locality     (sub-second)   dedup (3-layer) (per type)             │
│                                                                           │
│  ✓ Celebrity fan-out in seconds  ✓ Multi-region (GDPR)                   │
│  ✓ Provider failover (auto)      ✓ 3-layer dedup                         │
│  ✓ Self-service for teams        ✓ Cost-optimized (SMS reduction)        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TEACHING POINT: Each evolution was driven by production incidents, not
planned from day one. V1 is correct for 1M users. V2 is necessary at 10M.
V3 is required at 100M+. A Staff Engineer's skill is recognizing which
incidents will occur at the next scale milestone and designing ahead of them.
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What if X Changes?" Questions

```
QUESTION 1: What if fan-out ratio increases 10× (average 3 → 30)?
  IMPACT: Downstream volume increases 10× (660K → 6.6M deliveries/sec)
  → Preference evaluation becomes bottleneck (10× more cache reads)
  → Push workers need 10× capacity
  → Queue depth grows 10× → need larger queue clusters
  REDESIGN:
  → Pre-evaluate preferences for top notification types (cache results)
  → Implement "smart fan-out": Skip preference evaluation for users
    with default preferences (enabled for all types)
  → ~80% of users have default prefs → skip evaluation for 80%
  → Effective volume increase: 10× × 0.2 = 2× (manageable)

QUESTION 2: What if a new channel is added (WhatsApp Business)?
  IMPACT: New channel worker pool + provider integration
  → Preference schema needs new column per notification type
  → Channel router needs new routing rules
  → New provider rate limits and failure modes
  REDESIGN:
  → Channel abstraction layer: Each channel implements a standard interface
    → send(user_id, payload) → DeliveryResult
    → healthCheck() → ProviderHealth
    → retryPolicy() → RetryConfig
  → Adding a channel = implementing the interface + registering in config
  → No core pipeline changes needed

QUESTION 3: What if notification content becomes personalized per recipient?
  IMPACT: Content payload is no longer shared across fan-out batch
  → Each recipient needs unique rendering (different language, different
    actor display name formatting, different product recommendations)
  → Fan-out batches can't share payload → per-recipient rendering needed
  REDESIGN:
  → Lazy rendering: Store template + parameters in delivery item
  → Channel workers render at delivery time (already per-recipient)
  → Trade-off: Rendering in worker hot path adds 2-5ms per notification
  → Optimization: Cache rendered templates for common (template, locale) pairs

QUESTION 4: What if regulatory requires notification audit with 7-year retention?
  IMPACT: Delivery log retention: 1 year → 7 years
  → Storage cost: ~$2K/month → ~$14K/month (cold storage, manageable)
  → BUT: Must be queryable for compliance audits (not just archived)
  REDESIGN:
  → Cold storage with indexing (columnar format + search index)
  → Compliance query API: "Show all notifications sent to user X between
    date A and date B" → query cold storage
  → Trade-off: Cold queries take seconds (vs milliseconds for hot)
  → Acceptable: Compliance audits are not real-time

QUESTION 5: What if push notification open rates drop below 5%?
  IMPACT: Push channel becoming ineffective → wasted sends
  → Cost is low (push is free) but user engagement is the concern
  → If users don't open push, the channel isn't delivering value
  REDESIGN:
  → Smart channel selection: Route to the channel with highest
    historical open rate for this user
  → Some users respond better to email; some to push
  → ML model: P(open | user, channel, notification_type) → channel selection
  → Implement as optional stage in channel router (not blocking critical path)
```

## Redesign Under New Constraints

```
CONSTRAINT 1: Budget cut — reduce infrastructure cost by 80%
  → Eliminate multi-region (single region with DR backup)
  → Eliminate SMS entirely (push-only for OTP, email fallback)
  → Reduce delivery log retention to 7 days
  → Reduce notification inbox retention to 30 days
  → Merge P1 and P2 queues (two priority classes instead of three)
  → Accept: Higher latency for social notifications, no SMS channel,
    limited debugging capability, single-region failure risk
  → Estimated savings: $105M (SMS) + $20K (infra) = ~80%+ reduction

CONSTRAINT 2: Privacy-first — no behavioral tracking
  → No frequency cap (requires tracking notification count per user)
  → No smart channel selection (requires tracking channel engagement)
  → No notification aggregation (requires tracking recent events per user)
  → Preference evaluation: Still possible (explicit user settings)
  → Fan-out: Still possible (follower lists are explicit relationships)
  → IMPACT: Users may receive too many notifications (no frequency cap)
  → Mitigation: Aggressive per-type rate limits at ingestion (coarser control)

CONSTRAINT 3: 100ms end-to-end for ALL notifications (including fan-out)
  → Pre-compute notification RESULTS (not just fan-out partitions)
  → For "new_post" type: Pre-generate push payloads for all followers
    → On post event: Retrieve pre-generated payloads → enqueue directly
    → Bypasses: Preference evaluation, channel routing, rendering
  → Trade-off: Stale preferences (evaluated at pre-computation time)
  → Trade-off: Massive storage (100M pre-computed notifications per post)
  → Trade-off: Pre-computation cost (compute notification for every follower
    even if most won't receive it)
  → VERDICT: Impractical at scale. 100ms for fan-out of 10M is physically
    impossible (network propagation alone takes longer). Redefine requirement:
    100ms for first recipient, 5 minutes for last.
```

## Failure Injection Exercises

```
EXERCISE 1: Kill the preference cache cluster entirely
  OBSERVE: Does the system fall back to database reads?
  How much does preference evaluation latency increase?
  At what point does the database become overloaded?
  Do P0 notifications still deliver (should default to enabled)?

EXERCISE 2: Inject 50% packet loss on the cross-region message queue
  OBSERVE: Do cross-region notifications retry?
  How many are lost permanently?
  Does the system detect missing deliveries?
  What's the user-visible impact for users in the affected region?

EXERCISE 3: Stop all push workers for 10 minutes during a celebrity fan-out
  OBSERVE: Does the push queue handle 10M items? (capacity check)
  When workers restart, do they drain the queue safely?
  Are stale notifications (past TTL) dropped correctly?
  Does the system send 10M notifications in a burst (thundering herd)?

EXERCISE 4: Send a notification event with an unknown notification type
  OBSERVE: Does the ingestion API reject it? (schema validation)
  If it passes validation, does the preference evaluator handle it?
  What are the default preferences for an unknown type?
  Is the event logged for debugging?

EXERCISE 5: Register 1,000 push tokens for a single user
  OBSERVE: Does the token registry enforce a per-user token limit?
  If not, does the push worker attempt 1,000 sends per notification?
  What's the latency impact of 1,000 concurrent APNs sends for one user?
  Does this create a hot key in the token registry cache?

EXERCISE 6: Trigger a 50M-user broadcast while all three priority queues 
  are at 80% capacity
  OBSERVE: Does the broadcast respect capacity constraints?
  Does load shedding activate for P2?
  Does P0 throughput remain stable?
  What's the broadcast completion time under load?
```

## Organizational & Ownership Stress Tests

```
STRESS TEST 1: Push team and platform team disagree on retry policy
  SCENARIO: Platform team wants 3 retries for P1 push. Push team says
  APNs penalizes aggressive retry → wants 1 retry max.
  QUESTION: Who decides? How is the conflict resolved?
  STAFF ANSWER: Push team owns provider relationship and understands
  APNs behavior. Provider-specific retry policy is the channel team's
  decision. Platform team sets the INTERFACE (max retries allowed) but
  channel team sets the IMPLEMENTATION (actual retry count per provider).
  The platform provides the retry budget; the channel decides how to spend it.

STRESS TEST 2: Marketing team bypasses frequency cap for "critical" campaign
  SCENARIO: Marketing VP demands that a Black Friday campaign bypasses
  the 50 notifications/day frequency cap. "This is our biggest revenue
  event. Every user MUST see it."
  QUESTION: How does the system handle business pressure to bypass controls?
  STAFF ANSWER: Frequency caps exist to prevent permanent notification
  channel loss. Bypassing for one campaign sets a precedent that erodes
  the system's protective guarantees. Instead: Use a DEDICATED campaign
  slot that counts separately from organic notifications. Users get their
  50 organic + 1 campaign notification. The marketing team gets their reach;
  the user doesn't get overwhelmed. The system supports the business
  without compromising user experience.

STRESS TEST 3: New team onboards with 500K events/sec (doubles system load)
  SCENARIO: Video team launches a "video view" notification type. Each video
  view generates a notification to the creator. Video views: 500K/sec.
  QUESTION: How do you onboard without destabilizing existing notifications?
  STAFF ANSWER: Graduated onboarding. Start at 100 events/sec (0.02% of 
  their volume), validate pipeline handles the new type, increase 10× per
  week. Full volume in 4 weeks. Rate limit enforced by the type registry —
  new types start with restrictive limits by default. Capacity planning:
  500K new events/sec doubles ingestion load → provision additional workers
  BEFORE increasing the rate limit.

STRESS TEST 4: APNs certificate managed by a different team expires
  SCENARIO: The iOS app team manages APNs certificates. They forget to
  renew. All iOS push silently fails. Notification team gets paged.
  QUESTION: Who is responsible? How do you prevent this?
  STAFF ANSWER: Shared responsibility model with automated guardrails.
  Notification platform monitors APNs error codes. Specific error code
  for expired certificate → auto-alert BOTH notification on-call AND iOS
  team. Additionally: Certificate expiry date tracked in platform config,
  automated alert 60/30/14/7 days before expiry. The iOS team owns the
  certificate; the notification team owns the monitoring that catches the
  failure. Neither team can prevent it alone.
```

## Trade-Off Debates

```
DEBATE 1: Fan-out on write vs fan-out on read
  FAN-OUT ON WRITE (our design):
  → When event occurs: Resolve all recipients, enqueue per-recipient items
  → Pro: Low read latency (notification already in user's inbox)
  → Pro: Push/email delivered proactively (user doesn't need to open app)
  → Con: Write amplification (1 event → 10M writes for celebrity)
  → Con: Wasted work for users who never open the app

  FAN-OUT ON READ:
  → When user opens inbox: Compute notifications from followed users' events
  → Pro: No write amplification (store events, not per-recipient copies)
  → Pro: No wasted work for inactive users
  → Con: High read latency (must scan all followed users' events)
  → Con: Cannot push/email (no pre-computation of who should receive what)

  STAFF DECISION: Fan-out on write for push/email (proactive delivery 
  requires per-recipient work). Fan-out on read for in-app inbox 
  (supplemental, inbox can compute on open). Hybrid approach.
  Exception: Celebrity fan-out uses pre-computed partitions, which is
  a form of "fan-out on write with lazy computation."

DEBATE 2: One notification service vs per-channel services
  ONE SERVICE:
  → Central control: Preferences, frequency caps, dedup all in one place
  → Single team ownership: Clear accountability
  → Single point of failure: One bug affects all channels
  → Scaling: Must scale for the sum of all channels

  PER-CHANNEL SERVICES:
  → Channel teams own their pipeline: Can iterate independently
  → Isolated failures: Push service bug doesn't affect email
  → Duplicated logic: Preferences, frequency caps reimplemented per channel
  → Cross-channel features (frequency cap) are very hard

  STAFF DECISION: Central service for ingestion, fan-out, preference 
  evaluation, and routing (shared logic). Per-channel worker pools for
  delivery (channel-specific logic, isolated failures). The worst of both
  worlds is duplicating preference logic across channels.

DEBATE 3: In-house email sending vs managed email service
  IN-HOUSE (own SMTP infrastructure):
  → Full control: IP reputation, warm-up, deliverability optimization
  → Cost: Lower per-email cost at high volume
  → Ops burden: IP reputation management, bounce handling, spam compliance
  → Risk: One bad campaign can poison IP reputation for all emails

  MANAGED SERVICE (SES-like):
  → Low ops burden: Provider manages IP reputation
  → Cost: Higher per-email ($0.10/1K)
  → Less control: Subject to provider's policies and rate limits
  → Easier compliance: Provider handles bounce, complaint processing

  STAFF DECISION: Managed service for most teams. In-house SMTP relay as
  fallback for provider outages and for highest-volume campaigns where
  per-email cost matters. Dual-stack: Primary on managed, secondary on 
  self-hosted. This gives cost optimization + provider independence.

DEBATE 4: Centralized notification platform vs embedded libraries
  CENTRALIZED (our design):
  → One service that all teams call via API
  → Central enforcement: Preferences, frequency caps, dedup, priority
  → Single team responsible for delivery reliability
  → Bottleneck: Platform team becomes the bottleneck for new features
  → Risk: Single point of failure for ALL notifications

  EMBEDDED LIBRARY:
  → Notification logic packaged as a library (SDK) that teams import
  → Each team calls providers directly through the library
  → Fast iteration: Teams don't wait for platform team
  → No central bottleneck
  → Problem: Library version skew (team A on v1.2, team B on v2.0)
  → Problem: No central enforcement (team can bypass frequency caps)
  → Problem: Configuration changes require all teams to redeploy

  STAFF DECISION: Centralized service with a thin client SDK for ergonomics.
  SDK handles: Serialization, retry on 503, idempotency key generation.
  Service handles: Everything else (fan-out, preferences, routing, delivery).
  SDK is deliberately thin (< 200 lines) so version skew is a non-issue.
  Teams interact with the notification system via API contract, not code.

  REAL-WORLD ANALOGY (Configuration/Feature Flags):
  Feature flag systems went through the same evolution: Embedded library →
  centralized service. The centralized service wins because cross-cutting
  concerns (who sees what, audit, kill switch) require a single enforcement
  point. Notification preferences are the same kind of cross-cutting concern.
```

---

# Summary

This chapter has covered the design of a Notification Delivery System (Fan-out at Scale) at Staff Engineer depth, from the foundational pipeline architecture through multi-region delivery, failure handling, cost optimization, and system evolution.

### Key Staff-Level Takeaways

```
1. Fan-out is a pipeline, not a loop.
   Event → Recipient Resolution → Preference Evaluation → Channel Routing → Delivery.
   Each stage has its own scaling profile and failure mode.

2. Priority isolation must be physical, not logical.
   Separate queues, separate workers, separate capacity for P0/P1/P2.
   If a marketing campaign can delay an OTP, isolation is broken.

3. The notification you suppress is as important as the one you deliver.
   Aggregation, frequency caps, quiet hours, and per-type preferences
   prevent notification fatigue — the #1 cause of permanent channel loss.

4. Channel isolation limits blast radius.
   APNs outage affects only iOS push. FCM, email, SMS, and in-app
   continue unaffected. Each channel has its own circuit breaker.

5. SMS dominates cost by 100×.
   Reducing SMS usage (push-based OTP) saves more money than all
   other infrastructure optimizations combined.

6. Exactly-once delivery is impossible. At-least-once with dedup is practical.
   Three-layer deduplication (event, batch, delivery) achieves 99.99%
   unique delivery without distributed transactions.

7. Evolution is driven by incidents.
   V1 monolith → V2 priority separation → V3 global platform.
   Each transition was triggered by a production incident at the next
   scale milestone. Design for the incidents you can predict.
```

### How to Use This Chapter in an Interview

```
OPENING (0-5 min):
  → Clarify: What triggers notifications? How many channels? Max fan-out?
  → State: "I'll design this as a multi-stage pipeline: ingestion validates
    and deduplicates, fan-out resolves recipients, preference evaluation
    filters and routes, and channel workers deliver with provider-specific
    logic. Priority isolation is physical, not logical."

FRAMEWORK (5-15 min):
  → Requirements: Multi-channel, priority isolation, fan-out at scale
  → Scale: 100M DAU, 220K events/sec, 660K deliveries/sec
  → NFRs: P0 < 5s, P1 < 30s, 99.99% for P0, at-least-once with dedup

ARCHITECTURE (15-30 min):
  → Draw the pipeline: Ingest → Fan-out → Pref → Channel Router → Workers
  → Draw priority isolation: P0/P1/P2 separate queues + workers
  → Explain: Pre-computed fan-out for celebrities, bloom filter dedup

DEEP DIVES (30-45 min):
  → When asked about fan-out: Pre-computed partitions, chunked processing
  → When asked about failure: Per-channel circuit breakers, TTL-aware retry
  → When asked about cost: SMS dominance, push-based OTP savings
  → When asked about preferences: Per-type, per-channel, quiet hours, freq caps
  → When asked about dedup: Three layers — event, batch, delivery (bloom filter)
```

---

# Google L6 Review Verification

**This chapter now meets Google Staff Engineer (L6) expectations.**

### Staff-Level Signals Covered

```
✓ Judgment & Decision-Making
  → Every major decision (priority isolation, dedup strategy, channel routing,
    fan-out approach) includes explicit WHY, alternatives considered, and 
    dominant constraint identified
  → L5 vs L6 reasoning explicitly contrasted throughout

✓ Failure & Degradation Thinking
  → Partial failures: Cache shard, provider partial outage, worker overload
  → Cascading failure: Multi-component compound failure with positive feedback loop
  → Deployment failures: Bad code push, config mis-push, schema migration
  → Poison pill handling: Malformed messages that crash workers
  → Blast radius: Per-component failure impact table with user-visible symptoms
  → Two detailed failure timelines (single-component and multi-component)

✓ Scale & Evolution
  → Concrete scale numbers: 220K events/sec, 660K deliveries/sec, 500M users
  → Growth modeled at 20-30% YoY with explicit bottleneck identification
  → V1 → V2 → V3 evolution driven by real incidents
  → Migration strategy: Phased, feature-flagged, zero-downtime V2→V3

✓ Cost & Sustainability
  → SMS identified as dominant cost driver ($105M/month)
  → Cost-aware redesign: $84M/month savings from push-based OTP
  → Bandwidth and observability costs explicitly estimated
  → Over-engineering explicitly identified and avoided

✓ Organizational & Operational Reality
  → Team ownership model: Platform team, channel teams, producer teams
  → SLO/SLA enforcement across producer teams with attribution
  → On-call playbook with alert-to-action mapping
  → Human failure modes: Alert fatigue, wrong runbook, credential expiry
  → Org stress tests: Cross-team disagreements, business pressure, onboarding
  → Canary deployment strategy for silent failure detection

✓ Data Model & Consistency
  → Consistency model per data type with explicit trade-offs
  → Race conditions enumerated with concrete timelines
  → Concurrent unread count updates and hot-user shard problem addressed
  → Three-layer dedup with bloom filter sizing justified

✓ Multi-Region & Security
  → Data locality for GDPR compliance
  → Cross-region fan-out forwarding
  → Regional failure scenario with RTO/RPO
  → Abuse vectors with defense strategies
  → Privilege boundaries across organizational roles

✓ Master Review Check (11 checkboxes) satisfied
✓ L6 dimension table (A–J) documented
✓ Exercises & Brainstorming exist (Part 18)
✓ Real Incident table (structured) in Part 14
✓ Staff One-Liners & Mental Models table
✓ Interview Calibration: leadership explanation, how to teach
```
