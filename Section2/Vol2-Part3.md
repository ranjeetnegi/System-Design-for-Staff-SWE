# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 3: Phase 2 — Functional Requirements: Staff-Level Precision

---

# Quick Visual: The Functional Requirements Sweet Spot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   FUNCTIONAL REQUIREMENTS SWEET SPOT                        │
│                                                                             │
│   TOO VAGUE                    JUST RIGHT                    TOO DETAILED   │
│   ┌─────────────┐              ┌─────────────┐              ┌─────────────┐ │
│   │"System      │              │"Users can   │              │"Store in    │ │
│   │ handles     │      →       │ send text   │      ←       │ Cassandra   │ │
│   │ messages"   │              │ messages to │              │ with user_id│ │
│   │             │              │ other users"│              │ partition"  │ │
│   └─────────────┘              └─────────────┘              └─────────────┘ │
│        ↓                              ↓                            ↓        │
│   No design                    Drives design               Constrains       │
│   guidance                     decisions                   implementation   │
│                                                                             │
│   KEY: Describe WHAT the system does, not HOW it does it.                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Simple Example: Senior vs Staff Requirements

| Aspect | Senior (L5) Approach | Staff (L6) Approach |
|--------|---------------------|---------------------|
| **Level of detail** | "System sends notifications" | "Services submit notifications with recipient, content, channel; system delivers in near-real-time respecting user preferences" |
| **Prioritization** | Lists all features equally | "Core: send, deliver. Supporting: aggregation. Out of scope: A/B testing" |
| **Edge cases** | Happy path only | "If recipient offline, queue. If delivery fails, retry 3x. If user blocked sender, suppress." |
| **Scope** | Implicit or unclear | "In scope: delivery. Out of scope: content creation, analytics" |
| **Confirmation** | Moves straight to design | "Does this capture what you had in mind?" |

---

# Introduction

After understanding your users and their use cases, the next step is defining what the system actually does. This is Phase 2: Functional Requirements.

Functional requirements describe the behaviors and capabilities of your system. They answer the question: "What must this system do?" Not how it does it (that's architecture), not how well it does it (that's non-functional requirements), but what it does.

This sounds straightforward, and in some ways it is. But Staff-level precision in functional requirements is harder than it appears. Too vague, and your design has no foundation. Too detailed, and you've wasted precious interview time on specifications that don't matter. Too broad, and you'll never finish. Too narrow, and you've missed critical functionality.

Staff engineers hit the sweet spot: precise enough to drive design decisions, focused enough to fit the time available, complete enough to cover the core, and explicit enough about what's excluded.

This section will teach you how to define functional requirements with Staff-level precision. We'll cover what functional requirements really mean, how to distinguish core from supporting functionality, how to think about different types of system operations, how to handle edge cases explicitly, and how to avoid the feature creep that derails many designs.

---

# Part 1: What Functional Requirements Really Mean

## The Definition

Functional requirements describe what a system does—the capabilities it provides and the behaviors it exhibits. They are:

**Observable**: Users or other systems can see the effects
**Testable**: You can verify whether the system meets them
**Behavior-focused**: They describe what happens, not how it happens internally

Contrast with non-functional requirements, which describe qualities like performance, availability, and security. Functional requirements say "the system sends notifications"; non-functional requirements say "notifications are delivered within 5 seconds."

## Functional vs. Non-Functional: The Line

The distinction matters because functional and non-functional requirements drive different design decisions.

| Functional | Non-Functional |
|------------|----------------|
| Users can send messages | Messages are delivered within 1 second |
| Users can search their message history | Search returns results in under 200ms |
| Users can set notification preferences | Preferences take effect within 5 seconds |
| System logs all API calls | Logs are retained for 90 days |

When defining functional requirements, focus on the capability, not the quality. You'll address quality in Phase 4 (Non-Functional Requirements).

## Functional Requirements vs. Use Cases

Use cases describe user goals and workflows. Functional requirements describe system capabilities that enable those workflows.

**Use case**: "A user wants to message a friend."
**Functional requirements**:
- System allows users to compose and send messages
- System delivers messages to recipients
- System notifies recipients of new messages
- System stores messages for later retrieval

A single use case often requires multiple functional requirements. And a single functional requirement often supports multiple use cases.

## The Right Level of Detail

Functional requirements should be:

**Specific enough** to guide design decisions:
- ❌ "System handles messages" (too vague)
- ✅ "System allows users to send text messages up to 10,000 characters to other users"

**Abstract enough** to avoid implementation details:
- ❌ "System stores messages in a Cassandra table with user_id as partition key" (implementation)
- ✅ "System stores messages and allows retrieval by conversation"

**Bounded enough** to be achievable:
- ❌ "System handles all possible message types" (unbounded)
- ✅ "System handles text messages and image attachments"

---

# Part 2: Core vs. Supporting Functionality

## Quick Visual: Core vs Supporting

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CORE vs SUPPORTING FUNCTIONALITY                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  CORE FUNCTIONALITY (Design First, Most Carefully)                │     │
│   │                                                                   │     │
│   │  ✓ System is USELESS without it                                   │     │
│   │  ✓ Primary reason system exists                                   │     │
│   │  ✓ Users would abandon product without it                         │     │
│   │  ✓ Failure = emergency                                            │     │
│   │                                                                   │     │
│   │  Example (Messaging): Send message, receive message, view history │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  SUPPORTING FUNCTIONALITY (Fit Around Core)                       │     │
│   │                                                                   │     │
│   │  ✓ System WORKS without it (in diminished way)                    │     │
│   │  ✓ Enhances but not essential                                     │     │
│   │  ✓ Can have lower quality guarantees                              │     │
│   │  ✓ Failure = degradation (not emergency)                          │     │
│   │                                                                   │     │
│   │  Example (Messaging): Reactions, read receipts, typing indicators │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   TIME LIMITED? Cut supporting, keep core.                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Defining the Distinction

Not all functionality is equally important. Staff engineers distinguish:

**Core functionality**: The capabilities without which the system has no value. These define the system's essential purpose. If core functionality fails, the system is useless.

**Supporting functionality**: Capabilities that enhance the system but aren't essential to its basic operation. The system still works (in a diminished way) if these fail.

## Why This Matters

This distinction drives multiple decisions:

**Design priority**: Core functionality is designed first and most carefully. Supporting functionality fits around it.

**Quality investment**: Core functionality needs the highest reliability and performance. Supporting functionality can have lower guarantees.

**Scope management**: When time is limited, supporting functionality is what you cut.

**Failure modes**: Core functionality failures are emergencies. Supporting functionality failures are degradations.

## Identifying Core Functionality

Ask these questions:

**Would the system be useless without this?**
- Sending messages in a messaging system: Yes → Core
- Read receipts in a messaging system: No → Supporting

**Is this the primary reason the system exists?**
- Rate limiting in a rate limiter: Yes → Core
- Usage analytics in a rate limiter: No → Supporting

**Would users abandon the product without this?**
- Viewing the feed in a social app: Yes → Core
- Filtering the feed by content type: No → Supporting

## Examples Across Systems

### Messaging System

**Core functionality:**
- Send a message to a user or group
- Receive messages in real-time
- Retrieve conversation history

**Supporting functionality:**
- Message reactions (emoji)
- Read receipts
- Typing indicators
- Message search
- Message deletion/unsend

### Rate Limiter

**Core functionality:**
- Check if a request is within limits
- Enforce the limit (allow or reject)
- Track usage per client/endpoint

**Supporting functionality:**
- View current usage
- Configure limits via API
- Generate usage reports
- Alert on limit exhaustion

### Feed System

**Core functionality:**
- Generate a personalized feed for a user
- Render feed content
- Support pagination/infinite scroll

**Supporting functionality:**
- Feed filtering by content type
- Hiding/snoozing accounts
- Saving posts for later
- Feed refresh controls

## Articulating the Distinction in Interviews

Make your prioritization explicit:

"For this notification system, the core functionality is:
1. Accepting notification requests from services
2. Delivering notifications to users across channels
3. Respecting user preferences

Supporting functionality includes:
- Notification history/inbox
- Analytics on open rates
- A/B testing notification content

I'll design the core in detail. Supporting functionality will inform my data model but won't be fully designed unless we have time."

---

# Part 3: Read, Write, and Control Flows

## Quick Visual: The Three Flow Types

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        THE THREE FLOW TYPES                                 │
│                                                                             │
│   ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│   │     READ FLOWS      │  │    WRITE FLOWS      │  │   CONTROL FLOWS     │ │
│   │                     │  │                     │  │                     │ │
│   │  Retrieve data      │  │  Create/modify data │  │  Modify behavior    │ │
│   │  without modifying  │  │                     │  │  or configuration   │ │
│   ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤ │
│   │ • View messages     │  │ • Send a message    │  │ • Set rate limits   │ │
│   │ • Check rate limit  │  │ • Update profile    │  │ • Enable features   │ │
│   │ • Fetch user profile│  │ • Create a post     │  │ • Configure routing │ │
│   │ • Load feed         │  │ • Record an event   │  │ • Manage permissions│ │
│   ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤ │
│   │ Frequency: HIGHEST  │  │ Frequency: MEDIUM   │  │ Frequency: LOWEST   │ │
│   │ Latency: Often HIGH │  │ Latency: Variable   │  │ Latency: Usually LOW│ │
│   │ Consistency:Eventual│  │ Consistency: Strong │  │ Consistency: Strong │ │
│   │ Cacheable: YES      │  │ Cacheable: NO       │  │ Cacheable: Rarely   │ │
│   └─────────────────────┘  └─────────────────────┘  └─────────────────────┘ │
│                                                                             │
│   KEY: Don't forget control flows! They're often overlooked but critical.   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Three Flow Types

Most systems have three types of operations. Understanding these helps you enumerate functional requirements systematically.

**Read flows**: Operations that retrieve data without modifying it
- View messages
- Check rate limit status
- Fetch user profile
- Load feed

**Write flows**: Operations that create or modify data
- Send a message
- Update preferences
- Create a post
- Record an event

**Control flows**: Operations that modify system behavior or configuration
- Set rate limits
- Enable/disable features
- Configure routing rules
- Manage user permissions

## Why This Taxonomy Matters

Different flow types have different characteristics:

| Aspect | Read | Write | Control |
|--------|------|-------|---------|
| Frequency | Usually highest | Medium | Usually lowest |
| Latency sensitivity | Often high | Variable | Usually low |
| Consistency needs | Can be eventual | Often needs strong | Often needs strong |
| Failure tolerance | Can serve stale | Must not lose data | Must not corrupt state |
| Cacheability | Often cacheable | Not cacheable | Rarely relevant |

These differences drive design decisions. A system that's 99% reads might be designed completely differently from one that's 50% writes.

## Enumerating Flows Systematically

For each flow type, ask: "What operations exist?"

### Example: Notification System

**Read flows:**
- Fetch user preferences
- Get notification history for user
- Get delivery status of a notification
- View notification metrics (ops)

**Write flows:**
- Create/send a notification
- Mark notification as read
- Update user preferences
- Record delivery confirmation

**Control flows:**
- Enable/disable notification types
- Configure rate limits for notifications
- Set up routing rules (e.g., route to SMS if push fails)
- Manage channel configurations (APNs credentials, etc.)

### Example: Rate Limiter

**Read flows:**
- Check if request is allowed
- Get current usage for a client
- View configured limits

**Write flows:**
- Record a request (increment counter)
- Reset usage (periodic or manual)

**Control flows:**
- Configure rate limits
- Override limits for specific clients
- Enable/disable rate limiting
- Set up alerting thresholds

### Example: URL Shortener

**Read flows:**
- Resolve short URL to long URL
- Get analytics for a short URL
- List URLs created by a user

**Write flows:**
- Create a short URL
- Delete a short URL
- Record a click event

**Control flows:**
- Configure URL expiration policies
- Set up custom domain mappings
- Manage banned URL patterns

## Using Flows to Structure Requirements

In an interview, use this taxonomy to ensure completeness:

"Let me enumerate the functional requirements by flow type.

**Read flows:**
- Users can view their notification history
- Users can check their notification preferences
- Ops can view delivery metrics

**Write flows:**
- Services can send notifications to users
- Users can mark notifications as read
- Users can update their preferences

**Control flows:**
- Ops can configure notification routing
- Ops can enable/disable notification types

Does this cover the functionality you had in mind, or are there flows I'm missing?"

---

# Part 4: Defining Behavior Without Over-Specifying

## The Goldilocks Zone

Functional requirements need to be specific enough to be useful but not so detailed that they constrain implementation or waste time.

**Too vague:**
"System sends notifications"
- What triggers a notification?
- To whom?
- Through what channels?
- How do users control this?

**Too detailed:**
"When a user with ID matching pattern /^[a-z0-9]+$/ receives a message from a user they follow, and they have push_enabled=true in the preferences table, and they haven't been active in the last 5 minutes, send a push notification using Firebase Cloud Messaging with the message body truncated to 100 characters..."
- This is implementation, not requirements
- It constrains design unnecessarily
- It takes too long to articulate

**Just right:**
"When a triggering event occurs (like, comment, message, etc.), the system sends a notification to the affected user through their preferred channels, respecting their preference settings and suppression rules."
- Clear enough to understand what the system does
- Flexible enough to allow design choices
- Complete enough to identify key behaviors

## The Behavior Specification Pattern

A useful pattern for specifying behavior:

**When** [trigger condition] **the system** [action] **for** [affected entities] **according to** [relevant rules/conditions]

Examples:

"When a message is sent, the system delivers it to the recipient in real-time and stores it for later retrieval."

"When a request arrives, the system checks the client's usage against their configured limits and allows or rejects accordingly."

"When a user creates a short URL, the system generates a unique key and stores the mapping for the configured retention period."

## What to Specify vs. Leave Open

**Specify:**
- What triggers the behavior
- What the observable outcome is
- Who/what is affected
- What constraints or rules apply

**Leave open:**
- How the behavior is implemented
- What technologies are used
- Internal data representations
- Optimization strategies

**Example - Notification delivery:**

**Specify:**
- "Notifications are delivered to users in near-real-time"
- "Delivery occurs through the user's preferred channels"
- "Failed deliveries are retried up to 3 times"
- "Users can suppress notifications from specific sources"

**Leave open:**
- Whether to use push vs. pull for delivery
- The exact retry timing and backoff
- How preferences are stored and looked up
- The notification queueing mechanism

## Avoiding Premature Commitment

A common mistake is committing to details too early:

**Premature commitment:**
"The notification is stored in Cassandra with the user_id as partition key, then published to a Kafka topic, which triggers a consumer that calls the FCM API..."

**Why it's a problem:**
- You haven't validated that Cassandra, Kafka, or FCM are the right choices
- You're mixing requirements with design
- You're spending interview time on implementation details

**Better approach:**
"The notification needs to be stored durably and delivered in real-time. Let me first establish all the requirements, then I'll design the architecture to meet them. The choice of specific technologies will come from the requirements."

---

# Part 5: Handling Edge Cases Explicitly

## Quick Visual: Edge Case Triage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EDGE CASE TRIAGE FRAMEWORK                          │
│                                                                             │
│   For EACH edge case, decide:                                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  HANDLE FULLY: Design a complete solution                           │   │
│   │  → Use when: Frequent OR severe consequences                        │   │
│   │  → Example: "Message to offline user → Queue and deliver on online" │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  HANDLE GRACEFULLY: Provide degraded but acceptable behavior        │   │
│   │  → Use when: Rare but shouldn't crash the system                    │   │
│   │  → Example: "Content deleted mid-load → Show placeholder"           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  EXCLUDE EXPLICITLY: State this case is out of scope                │   │
│   │  → Use when: Very rare OR disproportionate complexity               │   │
│   │  → Example: "Sender deletes account → Messages stay, show 'deleted'"│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## What Are Edge Cases?

Edge cases are scenarios that deviate from the typical flow. They include:

**Unusual inputs**: Empty values, maximum values, invalid formats
**Error conditions**: Network failures, service unavailable, timeout
**Boundary conditions**: First item, last item, exactly at limit
**Race conditions**: Concurrent updates, out-of-order events
**Exceptional users**: Power users, inactive users, new users

## Why Edge Cases Matter

Edge cases reveal the true complexity of a system. A design that only handles the happy path will fail in production.

But edge cases can also be a trap. Trying to enumerate every possible edge case leads to analysis paralysis and wasted time.

Staff engineers find the balance: they identify significant edge cases, decide how to handle them (fully, gracefully, or explicitly exclude), and move on.

## The Edge Case Triage

For each edge case, decide:

**Handle fully**: Design a complete solution
- Use for: Edge cases that happen frequently or have severe consequences

**Handle gracefully**: Provide degraded but acceptable behavior
- Use for: Edge cases that are rare but shouldn't crash the system

**Exclude explicitly**: State that this case is out of scope
- Use for: Edge cases that are very rare or would add disproportionate complexity

## Identifying Significant Edge Cases

Ask these questions:

**What if inputs are extreme?**
- Empty list, zero value, maximum allowed value
- Very long strings, very large numbers
- Malformed data, unexpected types

**What if things fail?**
- Downstream service unavailable
- Database write fails
- Network timeout
- Partial failure (some operations succeed, some fail)

**What if timing is unusual?**
- Request received twice
- Events arrive out of order
- Update during read
- Stale data

**What if users are unusual?**
- Brand new user (no history)
- Extremely active user (10x normal volume)
- User who hasn't been active in years
- User at the exact limit

## Edge Cases by System Type

### Messaging System

| Edge Case | How to Handle |
|-----------|---------------|
| Message to self | Handle fully (allow it) |
| Empty message | Handle fully (reject with error) |
| Very long message | Handle fully (enforce limit, provide error) |
| Message to non-existent user | Handle fully (reject with clear error) |
| Message while recipient is offline | Handle fully (queue for later delivery) |
| Recipient blocks sender after message sent | Handle gracefully (deliver, but block future) |
| Message contains malicious content | Handle gracefully (content moderation, flag) |
| Exactly at rate limit | Handle fully (reject cleanly) |
| Sender deletes account after sending | Exclude (message remains, sender shows as "deleted user") |

### Rate Limiter

| Edge Case | How to Handle |
|-----------|---------------|
| First request ever | Handle fully (initialize counter) |
| Exactly at limit | Handle fully (reject this request) |
| Request from unknown client | Handle fully (use default limits or reject) |
| Limit changed while request in flight | Handle gracefully (use old or new, document which) |
| Clock skew across servers | Handle gracefully (tolerate small drift, document bounds) |
| Distributed counter inconsistency | Handle gracefully (may slightly over/under limit) |
| Limit set to zero | Handle fully (reject all requests) |
| Negative limit configured | Exclude (prevent at configuration time) |

### Feed System

| Edge Case | How to Handle |
|-----------|---------------|
| New user with no follows | Handle fully (show recommendations/trending) |
| User follows 100,000 accounts | Handle gracefully (limit considered sources) |
| User hasn't opened app in 1 year | Handle gracefully (fall back to trending + recent) |
| Post deleted after loaded in feed | Handle gracefully (show placeholder or filter on scroll) |
| Simultaneous scroll and new content | Handle fully (merge without disruption) |
| All followed accounts inactive | Handle gracefully (show recommendations) |
| Content flagged during feed generation | Handle gracefully (filter, refresh on next load) |

## Articulating Edge Cases in Interviews

Be explicit about your edge case decisions:

"Let me address a few edge cases.

**Messages to offline users**: I'll handle this fully—messages are queued and delivered when the user comes online.

**Very long messages**: I'll enforce a character limit. If exceeded, the client shows an error before sending.

**Sender blocks recipient after message sent**: I'll handle this gracefully—the message is delivered, but future messages are blocked. This is simpler than trying to recall an in-flight message.

**Sender deletes account**: I'm excluding this—if a sender deletes their account, their messages remain but the sender shows as 'deleted user.'

Are there other edge cases you'd like me to address?"

---

# Part 6: In-Scope vs. Out-of-Scope Decisions

## Quick Reference: Four Types of Scope Boundaries

| Boundary Type | What It Defines | Example |
|--------------|-----------------|---------|
| **Functional** | Which features are included | "Designing delivery, not search" |
| **User** | Which users are served | "For consumers, not admin users" |
| **Scale** | What scale range is addressed | "1-10M users, not 1B" |
| **Integration** | What's assumed to exist | "Auth exists; not designing it" |

**Key phrases:**
- "In scope: [X, Y, Z]"
- "Out of scope: [A, B, C]"
- "I'm assuming [D] exists"
- "Does this scope work for you?"

## The Purpose of Scope Boundaries

In an interview (and in real projects), you can't design everything. Scope boundaries define what you're responsible for and what you're not.

Clear scope boundaries:
- Focus your design effort
- Set expectations with the interviewer
- Prevent scope creep
- Enable integration assumptions

## Types of Scope Boundaries

### Functional Boundaries

What features are included vs. excluded:
- "I'm designing message delivery, not message search"
- "I'm designing notification sending, not notification content creation"
- "I'm designing the rate limiter, not the quota billing system"

### User Boundaries

Which users are served:
- "I'm designing for end consumers, not for admin users"
- "I'm designing for API clients, not for web UI"

### Scale Boundaries

What scale range is addressed:
- "I'm designing for 1-10 million users, not for 1 billion"
- "I'm designing for the initial launch, not for the 10-year vision"

### Integration Boundaries

What's assumed to exist vs. what's being built:
- "I'm assuming authentication exists; I'm not designing it"
- "I'm assuming we have a message queue; I'm not choosing which one"

## Making Scope Decisions

For each potential scope item, ask:

**Is this core to the problem?** If yes, it's in scope.

**Is this interesting or differentiating?** If yes, consider including it.

**Is this well-understood/standard?** If yes, consider excluding it.

**Does the interviewer seem interested?** If yes, include it.

**Do I have time?** If no, exclude it.

## Articulating Scope Clearly

Use explicit language:

**Positive scope (what's in):**
- "I will design..."
- "In scope for this design..."
- "I'm focusing on..."

**Negative scope (what's out):**
- "I'm explicitly not designing..."
- "Out of scope..."
- "I'm assuming this exists..."

**Scope rationale:**
- "I'm excluding [X] because it's a separate concern that's well-understood."
- "I'm including [Y] because that's where the interesting complexity is."

**Scope confirmation:**
- "Does this scope match what you had in mind?"
- "Should I include [X], or is my scope appropriate?"

## Example: Notification System Scope

"For this notification system, my scope is:

**In scope:**
- Accepting notification requests from internal services
- Storing notifications for later retrieval
- Delivering notifications via push and email
- Managing user preferences
- Basic delivery tracking

**Out of scope:**
- Creating notification content (done by calling services)
- Email and push infrastructure (using existing providers)
- Rich analytics (separate analytics system)
- A/B testing notification content (separate experimentation platform)
- Admin UI (assuming CLI/API for now)

**Assumptions:**
- Authentication/authorization is handled
- We have existing push (FCM/APNs) and email (SendGrid) integrations
- User data (names, emails, device tokens) is available from user service

Does this scope work?"

---

# Part 7: How Staff Engineers Avoid Feature Creep

## What Is Feature Creep?

Feature creep is the gradual expansion of scope beyond original boundaries. It happens when:
- You keep adding "just one more thing"
- You design for hypothetical future needs
- You can't say no to nice-to-have features
- You don't distinguish core from supporting functionality

## Why Feature Creep Is Dangerous

In interviews:
- You run out of time before covering the essentials
- Your design becomes shallow and spread thin
- You look unfocused and undisciplined

In real projects:
- Timelines slip
- Complexity increases
- Quality suffers
- The core product is delayed

## Staff-Level Discipline

Staff engineers avoid feature creep through:

### 1. Ruthless Prioritization

"I only have 45 minutes. What matters most?"

Rank everything: must-have, should-have, could-have, won't-have. Design only the must-haves in detail.

### 2. Explicit "Not Now" Lists

Instead of vaguely deferring things, explicitly list what's excluded:

"These features are valuable but out of scope for this design:
- Message search
- Message reactions  
- Read receipts

They can be added later without changing the core architecture."

### 3. Scope Checkpoints

Periodically reassess scope:

"I've been designing for 15 minutes. Let me check: am I still focused on core functionality? Have I drifted into supporting features?"

### 4. The "Do We Need This?" Question

For every feature, ask:
- "Do we need this for the system to work?"
- "Do we need this for the core use case?"
- "Would users accept V1 without this?"

If no, it's a candidate for exclusion.

### 5. Resisting the "While We're At It" Trap

"While we're building notifications, we could also add..."

This is where feature creep starts. The answer is usually: "We could, but we won't—let's stay focused."

## Feature Creep in Interviews

**Common pattern:**

Candidate is designing a messaging system. They cover:
- Message sending ✓
- Message delivery ✓
- Message history ✓

Then they keep going:
- "We should also add reactions..."
- "And read receipts..."
- "And typing indicators..."
- "And message search..."
- "And voice messages..."
- "And video calling..."

They run out of time having shallowly covered many features, with none designed well.

**Better pattern:**

"For core functionality, I'm focusing on sending, delivery, and history. Those are the must-haves for a messaging system.

Features like reactions, read receipts, and search are valuable but supporting. I'll note that the data model supports them, but I won't design them in detail.

Voice and video are out of scope—they're really a different system that could integrate with messaging.

Let me spend our time going deep on the core."

---

# Part 8: Functional Requirements for Common Systems

Let me provide detailed functional requirements for several common system design problems.

## Rate Limiter

### Core Functional Requirements

**F1: Rate Check**
- Given a client identifier and request details, determine if the request should be allowed
- Return allow/deny decision with remaining quota information

**F2: Rate Enforcement**
- When a request is allowed, record it against the client's quota
- When a request is denied, return appropriate error with retry-after information

**F3: Limit Configuration**
- Allow limits to be configured per client, per endpoint, or per client-endpoint combination
- Support different time windows (per second, per minute, per hour)

### Supporting Functional Requirements

**F4: Usage Query**
- Allow clients to check their current usage without making a request
- Allow operators to view usage across all clients

**F5: Manual Override**
- Allow operators to temporarily increase/decrease limits for specific clients
- Allow emergency block of specific clients

**F6: Limit Reset**
- Automatically reset usage counters at window boundaries
- Allow manual reset for specific clients

### Edge Cases Addressed

- Unknown client: Apply default limits
- Limit changed mid-window: New limit applies to new window
- Counter overflow: Reset counter (with logging)
- Distributed inconsistency: May allow slightly over limit (documented tolerance)

### Out of Scope

- Quota management (billing based on usage)
- Abuse detection beyond rate limiting
- Historical usage analytics

## Notification System

### Core Functional Requirements

**F1: Notification Ingestion**
- Accept notification requests from internal services
- Validate notification data (recipient, content, channel)
- Queue notifications for processing

**F2: Notification Delivery**
- Deliver notifications through specified channels (push, email, SMS)
- Handle delivery confirmations and failures
- Retry failed deliveries according to policy

**F3: User Preferences**
- Allow users to set notification preferences by type and channel
- Respect preferences when delivering notifications
- Allow users to mute specific sources

**F4: Notification Storage**
- Store notifications for later retrieval (inbox/history)
- Allow users to view, read, and dismiss notifications

### Supporting Functional Requirements

**F5: Notification Aggregation**
- Aggregate similar notifications ("5 people liked your post")
- Prevent notification spam to users

**F6: Delivery Tracking**
- Track delivery status (sent, delivered, read)
- Provide delivery metrics to sending services

**F7: Channel Fallback**
- If primary channel fails, attempt secondary channels
- Respect user preferences in fallback decisions

### Edge Cases Addressed

- Recipient offline: Queue and deliver when online (push), send immediately (email)
- Invalid recipient: Reject with error, notify sender
- Preference changed mid-delivery: Apply new preference to future notifications
- Very high volume (celebrity post): Rate limit fan-out, prioritize recent followers

### Out of Scope

- Notification content creation (done by sending services)
- Push/email infrastructure (external providers)
- Rich analytics and A/B testing

## Feed System

### Core Functional Requirements

**F1: Feed Generation**
- Generate a personalized feed for a logged-in user
- Include content from followed accounts
- Rank content by relevance and recency

**F2: Feed Rendering**
- Return feed content in paginated format
- Support efficient infinite scroll
- Handle mixed content types (posts, images, videos)

**F3: Feed Refresh**
- Detect new content since last load
- Allow user to refresh for new content
- Merge new content without disrupting position

### Supporting Functional Requirements

**F4: Feed Personalization**
- Apply user-specific ranking adjustments
- Learn from user interactions (likes, time spent)
- Support A/B testing of ranking algorithms

**F5: Feed Controls**
- Allow users to hide specific posts
- Allow users to mute specific accounts
- Allow users to snooze accounts temporarily

**F6: Content Injection**
- Inject ads into feed at appropriate intervals
- Inject recommendations for new accounts to follow

### Edge Cases Addressed

- New user (no follows): Show trending content and recommendations
- User follows 50,000 accounts: Limit content sources considered
- User inactive for 1 year: Fall back to trending + recent from top follows
- Content deleted after loaded: Show placeholder, filter on next load

### Out of Scope

- Content storage and creation (separate content service)
- Ad selection and targeting (separate ads platform)
- Detailed engagement analytics

## URL Shortener

### Core Functional Requirements

**F1: URL Creation**
- Accept a long URL and create a short URL
- Generate unique, unpredictable short keys
- Support optional custom short keys

**F2: URL Resolution**
- Given a short URL, return the corresponding long URL
- Support fast redirects (low latency)
- Handle expired or non-existent URLs gracefully

**F3: URL Management**
- Allow users to list their created URLs
- Allow users to delete/disable URLs
- Support URL expiration policies

### Supporting Functional Requirements

**F4: Click Analytics**
- Track click counts per URL
- Capture click metadata (time, referrer, geography)
- Provide analytics dashboard

**F5: Custom Domains**
- Support branded short domains
- Map custom domains to URL namespaces

### Edge Cases Addressed

- Collision in short key generation: Retry with new key
- URL already exists: Return existing short URL (optional deduplication)
- Malicious long URL: Check against blocklist, reject known malware
- Very long URL: Enforce reasonable limits (2048 characters)
- Expired URL: Return 404 with helpful message

### Out of Scope

- Marketing automation (email campaigns, etc.)
- QR code generation (separate utility)
- Deep linking for mobile apps

---

# Part 9: Phrasing Requirements in Interviews

## The Requirement Statement Pattern

A clear format for stating requirements:

**[User/System] can [action] [object] [optional: conditions/constraints]**

Examples:
- "Users can send text messages to other users"
- "Services can submit notifications with recipient, content, and channel"
- "Operators can configure rate limits per client, effective within 1 minute"

## Grouping Requirements

Organize requirements for clarity:

**By flow type:**
- "For read operations: ... For write operations: ... For control operations: ..."

**By user type:**
- "For end users: ... For internal services: ... For operators: ..."

**By priority:**
- "Core requirements: ... Supporting requirements: ... Nice-to-have: ..."

## Checking Completeness

After listing requirements, verify:

"Let me check completeness:
- Can users do all the things they need to do? [lists]
- Can services integrate as needed? [lists]
- Can operators manage the system? [lists]

Is there functionality I'm missing?"

## Confirming with the Interviewer

Always confirm your requirements:

"Based on my understanding, here are the functional requirements:
[lists requirements]

Does this capture what you had in mind? Is there anything you'd like me to add or remove?"

## Example: Complete Requirements Statement

"For the notification system, here are the functional requirements:

**Core (must design in detail):**
1. Services can submit notifications with recipient, content, and channel
2. System delivers notifications to users in near-real-time
3. System respects user preferences when delivering
4. Users can view their notification history
5. Users can manage their notification preferences

**Supporting (will acknowledge in design):**
6. System aggregates similar notifications
7. System tracks delivery status
8. System falls back to alternative channels on failure

**Out of scope:**
- Notification content creation
- Push/email infrastructure
- Rich analytics

Does this scope align with your expectations?"

---

# Part 10: Common Pitfalls and How to Avoid Them

## Pitfall 1: Requirements Too Vague

**The problem:**
"System handles notifications" doesn't tell you what the system actually does.

**Why it happens:**
Candidates want to move quickly to architecture. They assume requirements are "obvious."

**How to avoid:**
Force yourself to be specific. Use the pattern: "[User] can [action] [object]." If you can't fill in the blanks, you're not specific enough.

**Example:**
- ❌ "System handles messages"
- ✅ "Users can send text messages to other users, who receive them in real-time"

## Pitfall 2: Requirements Include Implementation

**The problem:**
"Messages are stored in Cassandra and delivered via Kafka" is implementation, not requirements.

**Why it happens:**
Experienced engineers naturally jump to solutions. They conflate what with how.

**How to avoid:**
Ask yourself: "Am I describing observable behavior, or internal mechanism?" Requirements describe behavior; implementation describes mechanism.

**Example:**
- ❌ "Messages are published to Kafka for async delivery"
- ✅ "Messages are delivered asynchronously with at-least-once guarantee"

## Pitfall 3: No Prioritization

**The problem:**
Listing 15 requirements with no distinction between essential and nice-to-have.

**Why it happens:**
Candidates don't want to "miss" anything. Prioritization feels like excluding things.

**How to avoid:**
Explicitly categorize: core, supporting, out-of-scope. Announce what you're optimizing for.

**Example:**
- ❌ "The system should send notifications, track delivery, aggregate similar ones, support A/B testing, provide analytics..."
- ✅ "Core: send and deliver notifications. Supporting: aggregation and tracking. Out of scope: A/B testing and analytics."

## Pitfall 4: Missing Edge Cases

**The problem:**
Only describing the happy path. "Users send messages" but what about failures, limits, invalid inputs?

**Why it happens:**
Happy path is the obvious case. Edge cases require more thought.

**How to avoid:**
Systematically ask: "What if input is invalid? What if something fails? What about boundaries?"

**Example:**
- ❌ "Users can send messages to other users"
- ✅ "Users can send messages to other users. If the recipient doesn't exist, return error. If message exceeds length limit, reject. If delivery fails, retry 3 times."

## Pitfall 5: Scope Creep

**The problem:**
Starting with 3 requirements and ending with 15 as you keep adding "one more thing."

**Why it happens:**
Each addition seems small. "While we're at it" thinking.

**How to avoid:**
Set scope explicitly at the start. Use a "not now" list for things you think of later. Periodically check if you've drifted.

**Example:**
- ❌ [Keeps adding features throughout the interview]
- ✅ "I defined 5 core requirements at the start. I've thought of 3 more nice-to-haves—I'll note them but not design them."

## Pitfall 6: Not Confirming with Interviewer

**The problem:**
Assuming your understanding is correct without checking.

**Why it happens:**
Candidates want to seem confident. Checking feels like uncertainty.

**How to avoid:**
Confirmation is not weakness; it's collaboration. Always check: "Does this capture what you had in mind?"

**Example:**
- ❌ [States requirements and immediately moves to design]
- ✅ "Here are my requirements. Does this match your expectations? Should I adjust the scope?"

## Pitfall 7: Requirements Don't Enable Use Cases

**The problem:**
Your requirements don't actually support the use cases you identified.

**Why it happens:**
Requirements and use cases were defined separately without checking alignment.

**How to avoid:**
After defining requirements, trace each use case: "Can a user accomplish [use case] with these requirements?"

**Example:**
- Use case: "User views conversation history"
- Required functionality: "System stores messages and allows retrieval by conversation"
- Check: ✅ Use case is enabled by requirements

## Pitfall 8: Ignoring Control/Admin Flows

**The problem:**
Focusing entirely on user-facing functionality, forgetting about system management.

**Why it happens:**
User flows are more interesting. Admin flows seem boring.

**How to avoid:**
Explicitly enumerate control flows: "What operations do administrators need? What configuration is required?"

**Example:**
- ❌ [Only describes user sending/receiving messages]
- ✅ "Users send and receive messages. Operators can configure message retention, view delivery metrics, and block abusive users."

---

# Brainstorming Questions

## Understanding Requirements

1. For a system you've built, can you list 5 core and 5 supporting functional requirements? What made them core vs. supporting?

2. Think of a project where requirements were unclear. How did that affect the design? What would clearer requirements have changed?

3. When have you seen a system fail because edge cases weren't considered? What was missed?

4. How do you distinguish functional requirements from non-functional requirements? Where's the line?

5. Take a feature you've built. What was the observable behavior (functional) vs. the quality targets (non-functional)?

## Scope and Prioritization

6. When have you successfully cut scope on a project? What enabled you to do that?

7. When have you experienced feature creep? What caused it and how could it have been prevented?

8. How do you decide what's in V1 vs. V2? What's your mental model?

9. Think of a system with too many features. Which would you remove to simplify it?

10. How do you say "no" to stakeholders who want more features?

## Flow Analysis

11. Take a familiar system. What are its read, write, and control flows? Is the balance what you'd expect?

12. Which flow type is typically the bottleneck: read, write, or control? Why?

13. For a system you know, what's the ratio of reads to writes? How does that affect the design?

14. What control flows do people often forget to design? Why are they overlooked?

15. How do you ensure control flows are secure? What's the threat model?

---

# Homework Exercises

## Exercise 1: Requirements Specification

Take three system prompts:
1. "Design a rate limiter"
2. "Design a notification system"
3. "Design a URL shortener"

For each, write:
- 5 core functional requirements
- 3 supporting functional requirements
- 3 explicit exclusions (out of scope)
- 3 edge cases and how to handle them

Use the format: "[User/System] can [action] [object] [constraints]"

## Exercise 2: Core vs. Supporting Analysis

Take a product you use daily (e.g., Slack, Uber, Instagram).

List 10 features. For each, classify as:
- Core: Product is useless without it
- Supporting: Enhances but not essential
- Nice-to-have: Could remove without much impact

Now imagine you're building V1 with 50% of the features. Which 5 do you build?

## Exercise 3: Flow Enumeration

Pick a system (or use: Stripe, Dropbox, Spotify).

Enumerate all the flows you can identify:
- At least 5 read flows
- At least 5 write flows
- At least 3 control flows

For each flow, note:
- Who initiates it
- What data is involved
- What the expected outcome is

## Exercise 4: Edge Case Catalog

For a messaging system, enumerate edge cases across these categories:
- Invalid inputs (at least 5)
- Failure conditions (at least 5)
- Boundary conditions (at least 3)
- Timing/concurrency issues (at least 3)

For each, decide: handle fully, handle gracefully, or exclude?

## Exercise 5: Scope Negotiation

Practice scope negotiation with a partner.

Partner gives you an intentionally broad prompt:
"Design a complete social media platform."

Your task: negotiate it down to something designable in 45 minutes.

Practice:
- Asking clarifying questions to narrow scope
- Proposing boundaries and getting agreement
- Explicitly listing exclusions
- Confirming the scope before designing

## Exercise 6: Requirements-to-Use-Case Mapping

Take your requirements from Exercise 1.

For each use case you identified in Phase 1 (users & use cases), trace:
- Which requirements enable this use case?
- Are any use cases unsupported by requirements?
- Are any requirements not linked to use cases?

This validates that your requirements and use cases are aligned.

---

# Quick Reference Card

## Functional Requirements Checklist

| Step | Question to Ask | Example Output |
|------|-----------------|----------------|
| **Define what, not how** | "What does the system do?" | "Users can send messages" (not "stores in Cassandra") |
| **Identify core vs supporting** | "Is system useless without this?" | Core: send/receive. Supporting: reactions |
| **Enumerate all flow types** | "What are read, write, control flows?" | Read: view history. Write: send. Control: configure |
| **Handle edge cases** | "What if X fails/is extreme?" | "If offline, queue. If too long, reject." |
| **Set scope boundaries** | "What's in? What's out?" | "In: delivery. Out: analytics" |
| **Confirm with interviewer** | "Does this match your expectations?" | Get explicit agreement |

---

## The Requirement Statement Pattern

**Format:** `[User/System] can [action] [object] [optional: conditions/constraints]`

| ❌ Too Vague | ✅ Just Right |
|-------------|---------------|
| "System handles messages" | "Users can send text messages to other users" |
| "System does notifications" | "Services submit notifications; system delivers via push/email respecting preferences" |
| "System limits requests" | "System checks client usage against configured limits; allows or rejects accordingly" |

---

## Quick Reference: Behavior Specification Pattern

**When** [trigger] **the system** [action] **for** [affected entities] **according to** [rules]

**Examples:**
- "When a message is sent, the system delivers it to the recipient in real-time and stores it for later retrieval."
- "When a request arrives, the system checks the client's usage against limits and allows or rejects accordingly."
- "When a user creates a short URL, the system generates a unique key and stores the mapping."

---

## Edge Case Quick Reference

| Category | Questions to Ask | Example |
|----------|-----------------|---------|
| **Extreme inputs** | Empty? Max value? Very long? | "What if message is 100KB?" |
| **Failures** | Service down? Timeout? Partial failure? | "What if push delivery fails?" |
| **Timing** | Out of order? Concurrent? Stale? | "What if user updates preference mid-delivery?" |
| **Unusual users** | New user? Power user? Inactive? | "What if user follows 50,000 accounts?" |

---

## Common Pitfalls Quick Reference

| Pitfall | What It Looks Like | Fix |
|---------|-------------------|-----|
| **Too vague** | "System handles messages" | Use pattern: [User] can [action] [object] |
| **Includes implementation** | "Store in Cassandra, publish to Kafka" | Describe behavior, not mechanism |
| **No prioritization** | 15 requirements, all equal | "Core: X, Y. Supporting: Z. Out of scope: W" |
| **Missing edge cases** | Only happy path | Ask: "What if fails? What if extreme?" |
| **Scope creep** | Started with 3, ended with 15 | Set scope explicitly, use "not now" list |
| **No confirmation** | Assumes understanding is correct | "Does this capture what you had in mind?" |
| **Missing control flows** | Only user-facing features | "What do operators/admins need?" |

---

## Self-Check: Did I Cover Phase 2?

| Signal | Weak | Strong | ✓ |
|--------|------|--------|---|
| **Specificity** | "System handles X" | "[User] can [action] [object]" | ☐ |
| **Core/Supporting** | All requirements equal | "Core: A, B. Supporting: C, D" | ☐ |
| **Flow types** | Only obvious user flows | Read, Write, AND Control flows | ☐ |
| **Edge cases** | Happy path only | 3-5 edge cases with handling decisions | ☐ |
| **Scope** | Implicit | "In scope: X. Out of scope: Y" | ☐ |
| **Confirmation** | Moved straight to design | "Does this match expectations?" | ☐ |

---

# Conclusion

Functional requirements are the bridge between understanding your users (Phase 1) and designing your system (later phases). They define what you're building.

Staff-level precision in functional requirements means:

**Being specific enough** to drive design decisions—not vague hand-waving like "system handles messages"

**Being abstract enough** to avoid implementation details—not premature commitment to technologies

**Distinguishing core from supporting**—knowing what's essential vs. what's nice-to-have

**Covering all flow types**—read, write, and control, not just the obvious user flows

**Handling edge cases explicitly**—not just the happy path

**Managing scope actively**—saying no to feature creep, being explicit about exclusions

**Confirming alignment**—checking with the interviewer that your requirements match their expectations

The functional requirements you define in this phase become the contract for your design. Every architectural decision should trace back to a requirement. If you find yourself designing something that isn't required, question whether you need it.

Get the requirements right, and the design becomes clearer. Get them wrong, and you'll build the wrong system—no matter how elegant your architecture.

Take the time to be precise. It's a Staff-level habit.

---
