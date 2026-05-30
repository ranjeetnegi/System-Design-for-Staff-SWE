# Chapter 6: Core Building Blocks — Hash, Cache, State, Idempotency, Queues, Sync/Async

---

## 1. Learning Goal

After reading this chapter, you will be able to:

- Explain how hash functions distribute data evenly across servers
- Describe consistent hashing and why it is better than simple modulo hashing
- Design a caching strategy with the correct cache pattern, TTL, and invalidation approach
- Explain the difference between stateful and stateless services, and why it matters for scaling
- Implement idempotency for critical write operations (payments, orders)
- Choose between synchronous and asynchronous communication for a given use case
- Use queues to decouple producers and consumers, absorb traffic spikes, and process work reliably

---

## 2. Why This Matters

Every distributed system is built from a small set of fundamental patterns. If you are designing a payment system and you do not think about idempotency, a network timeout will double-charge users. If you are designing a feed system and you do not understand caching, your database will crash under load. If you use stateful servers without understanding the consequences, you cannot scale horizontally.

These building blocks are not academic — they appear in every real system. Staff engineers do not just use them; they choose them deliberately, explain the trade-offs, and know what breaks when any piece fails.

This chapter teaches you these six building blocks deeply:

1. **Hash functions** — how to distribute data evenly
2. **Caching** — how to make reads fast without overloading databases
3. **State vs stateless** — where to store session data
4. **Idempotency** — how to make operations safe to retry
5. **Queues** — how to decouple and buffer work
6. **Sync vs async** — when to wait and when to fire-and-forget

---

## 3. Core Concepts

### Part 1: Hash Functions

#### What Is a Hash Function?

A **hash function** takes any input (a string, a number, an object) and produces a fixed-size output called a **hash** or **digest**.

Important properties:
- **Deterministic**: The same input always produces the same output
- **Fixed output size**: Whether you hash 1 byte or 1 GB, the output is always the same size
- **One-way** (for cryptographic hashes): Given the hash, you cannot figure out the original input

Example: SHA-256("hello") always produces the same 64-character hexadecimal string, no matter where or when you run it.

---

#### Hash Functions in System Design

| Use case | How hash is used |
|----------|----------------|
| **Sharding** | `hash(user_id) % N` → which shard to use |
| **Load distribution** | `hash(key) % servers` → which server handles this key |
| **Caching** | hash(query parameters) → cache key |
| **Integrity checking** | hash(file content) → fingerprint for detecting corruption |
| **Password storage** | hash(password + salt) → store hash, never the password |

---

#### The Problem with Simple Modulo Hashing

The simplest way to assign keys to servers: `server = hash(key) % N` where N is the number of servers.

**Problem:** When N changes (you add or remove a server), almost all keys get reassigned.

Example: You have 10 servers. A key is assigned to server 3 (`hash(key) % 10 = 3`). You add an 11th server. Now `hash(key) % 11 = 7`. The key is now on server 7 — a different server. This happens for about 90% of all keys.

For a cache, this means 90% of your cache becomes invalid simultaneously when you add a server. All those requests suddenly hit the database — this is called a **thundering herd** and can crash your database.

---

#### Consistent Hashing: The Solution

**Consistent hashing** minimizes key movement when servers are added or removed.

**How it works:**

Imagine a circle (ring) with positions from 0 to 2^32. Both keys and servers are placed on this ring using their hash values.

```
                    0 / 2^32
                        │
              Node C ●──┼──● Node A
                   ╲    │   ╱
                    ╲   │  ╱
                Key1 ●  │  ● Key2
                    ╱   │  ╲
                   ╱    │   ╲
              Node D ●──┼──● Node B
                        │
```

A key belongs to the first server you encounter when going clockwise from the key's position on the ring.

**Adding a server:** Only the keys between the new server and its predecessor (counterclockwise neighbor) move to the new server. About 1/N of all keys move, not all of them.

**Removing a server:** Only that server's keys move to the next server clockwise. About 1/N of keys move.

With 10 servers, adding a server moves only ~10% of keys. With simple modulo, 90% would move.

**Virtual nodes:** In practice, each physical server is placed on the ring multiple times (100–200 times) at different positions, called **virtual nodes**. This makes the distribution more even, because in a small ring with few servers, one server might get more than its fair share of keys by chance. Virtual nodes smooth this out.

---

#### When to Use Consistent Hashing

Consistent hashing is standard for:
- Distributed caches (Memcached, Redis Cluster)
- Distributed databases (Cassandra, DynamoDB, Dynamo-like systems)
- Any system where you need to distribute keys across servers and add/remove servers without massive disruption

---

### Part 2: Caching

#### What Is a Cache?

A **cache** is a fast, temporary copy of data that is expensive to compute or slow to retrieve.

**The analogy:** Your desk vs. the filing cabinet. You keep frequently-used files on your desk for quick access. When you need a file, you check your desk first. If it is there (a **cache hit**), you use it immediately. If not (a **cache miss**), you go to the filing cabinet (the database), get it, and optionally put a copy on your desk.

**Why caching matters:** If 95% of reads hit the cache and only 5% reach the database, the database handles 20x less load. A system that would need 100 database replicas might need only 5 with effective caching.

---

#### Cache-Aside: The Most Common Pattern

The application (not the cache) is responsible for managing the cache.

```
1. Request comes in for key K
2. Check cache: Is K in the cache?
3a. YES (cache hit): Return cached value immediately
3b. NO (cache miss): 
      → Query database for K
      → Store result in cache (for future requests)
      → Return result
```

When data changes (a write happens):
- **Invalidation**: Delete the key from the cache. Next request will be a cache miss and will load fresh data from the database.
- **Update**: Write the new value to the cache immediately.

**Most applications use cache-aside with invalidation on write** because it is simple and correct.

---

#### Other Cache Patterns

| Pattern | How it works | When to use |
|---------|-------------|-------------|
| **Write-through** | Every write goes to both cache and database simultaneously | When you need the cache to always be up-to-date |
| **Write-behind** | Write to cache immediately, then write to database asynchronously later | When write speed is critical and you can tolerate some risk of data loss |
| **Read-through** | The cache layer (not the application) fetches from database on a miss | When you use a smart proxy cache |
| **Write-around** | Bypass the cache entirely on writes, only cache on reads | Write-heavy data that is rarely read |

---

#### TTL: Time To Live

Every cached entry should have a **TTL (Time To Live)** — the duration after which the cache automatically discards the entry.

When the TTL expires, the next request will be a cache miss and will fetch fresh data.

**Choosing TTL:**

| Data type | Acceptable staleness | TTL |
|-----------|---------------------|-----|
| Product prices | Minutes | 1–5 minutes |
| User profile (name, photo) | Hours | 1–6 hours |
| Product description | Days | 24–72 hours |
| Static content (JS, CSS) | Days to weeks | 1 day to 1 week |
| Session data | Until logout | 24 hours (or session duration) |

**Trade-off:** Shorter TTL → more cache misses → more database load, but fresher data. Longer TTL → higher hit rate → less database load, but potentially stale data.

---

#### Cache Invalidation: The Hard Problem

The famous saying: "There are only two hard things in computer science: cache invalidation and naming things."

**Why it is hard:**

When data changes in the database, you must ensure the cache reflects the change. But:
- If you invalidate too aggressively, you lose most of your cache hit rate
- If you miss an invalidation, users see stale data
- In distributed systems, you may have multiple cache replicas that all need invalidating

**Common strategies:**
1. **TTL-based expiry**: Do not explicitly invalidate. Let the TTL handle it. Accept that data may be stale for up to TTL seconds. Simple. Good for data that can tolerate some staleness.
2. **Invalidate on write**: When you write to the database, also delete the cache key. Next read will refresh it. More complex but keeps cache more consistent.
3. **Write-through**: Every write goes through the cache. Cache is always fresh. Higher write overhead.

---

#### Cache Stampede (Thundering Herd)

**The problem:** A popular cache entry expires at time T. In the next millisecond, 10,000 requests arrive and all miss the cache simultaneously. All 10,000 requests hit the database at once — potentially crashing it.

**Mitigations:**
- **Locking**: The first request acquires a lock, fetches from DB, updates cache. All others wait or return the slightly stale value.
- **Probabilistic early expiry**: Shortly before TTL expires, some requests probabilistically refresh the cache early, avoiding a sudden spike.
- **Background refresh**: Before TTL expires, a background job refreshes the cache. The old value is served until the refresh completes.

---

#### Hot Keys

A **hot key** is a cache key that receives disproportionately high traffic. Example: A celebrity's profile page is viewed by millions of users per minute. All requests go to the same cache key on the same cache node, making that one node the bottleneck.

**Solutions:**
- **Replicate the hot key** across multiple cache nodes. Read from a random node.
- **Local in-process cache**: Each application server has a small in-memory copy of extremely hot keys.

---

### Part 3: State vs Stateless

#### Stateful Servers

A **stateful** server stores information between requests — for example, user session data stored in server memory.

**The problem with stateful servers:**

```
Request 1 → Server A (stores session in memory)
Request 2 → Load balancer → Server B (does not have the session!) → Error
```

For this to work, you need **sticky sessions**: always route the same user to the same server. But this makes scaling harder — if Server A is overloaded, you cannot move users from it to Server B because their sessions are on A.

If Server A crashes, all users whose sessions were stored on it are logged out and lose their work.

---

#### Stateless Servers

A **stateless** server does not store anything between requests. Every request contains all the information needed to process it. If the server needs session data, it fetches it from an external store.

```
Request 1 → Any Server → Fetch session from Redis → Process → Response
Request 2 → Any Server → Fetch session from Redis → Process → Response
```

**Benefits:**
- Any server can handle any request — no sticky sessions needed
- Load balancer can distribute freely
- Adding servers immediately increases capacity
- Server failure loses no data (data is in the external store)

---

#### Where to Put State

The standard pattern: **stateless application servers + stateful external stores**

- Sessions → Redis (fast, with TTL)
- User data → Database (persistent, queryable)
- Temporary calculations → In-memory within the request, not across requests

**JWT vs Session Tokens:**

| Approach | Where state lives | Notes |
|----------|------------------|-------|
| **Session token (server-side)** | Redis, keyed by session ID | Easy to revoke (delete the Redis key). One Redis lookup per request. |
| **JWT** (JSON Web Token) | Inside the token itself | No server lookup needed — stateless! But hard to revoke before expiry. |

**Practical guidance:** Use JWTs for APIs with short-lived tokens (15–60 minutes). Use server-side sessions for applications where you need instant revocation (e.g., "log out all devices").

---

### Part 4: Idempotency

#### What Is Idempotency?

An operation is **idempotent** if doing it multiple times produces the same result as doing it once.

Real-world analogy: Pressing an elevator button. You press "Floor 5" once, and the elevator goes to floor 5. You press it again — nothing changes. The second press is idempotent.

**In HTTP:**
- `GET /users/123` → Idempotent (reading does not change state)
- `DELETE /users/123` → Idempotent (after first delete, user is gone; second delete just returns "not found")
- `POST /orders` → **NOT idempotent** (each call creates a new order)

---

#### Why Idempotency Is Critical for Writes

Networks are unreliable. Clients time out, servers restart, load balancers retry requests. When a client does not receive a response, it does not know if the server processed the request or not. So it retries.

**Without idempotency:**
1. Client sends "Charge $100"
2. Server charges $100 and prepares response
3. Network failure — client never receives the response
4. Client retries: "Charge $100" again
5. Server charges $100 again
6. **User is charged $200** ❌

**With idempotency keys:**
1. Client generates a unique ID: `key = "abc-123-xyz"`
2. Client sends "Charge $100, idempotency_key = abc-123-xyz"
3. Server checks: "Have I already processed abc-123-xyz?" → No → Process it. Store the result.
4. Network failure — client never receives the response
5. Client retries: "Charge $100, idempotency_key = abc-123-xyz"
6. Server checks: "Have I already processed abc-123-xyz?" → **Yes** → Return stored result
7. **User is charged $100 exactly once** ✅

---

#### How to Implement Idempotency Keys

**The mechanism:**

1. Client generates a unique ID (UUID) for each logical operation
2. Client includes it in every request: `Idempotency-Key: abc-123`
3. Server checks the key in a store (Redis or database) before processing
4. If the key already exists → return the stored response (no processing)
5. If the key does not exist → process, then store key + result (with a TTL, e.g. 24 hours)

**Rule:** One idempotency key per logical user action. "Place order" = one key. Do not reuse keys for different operations.

**Storage:** Store keys in Redis with a 24-hour TTL. After 24 hours, a retry with the same key might be treated as a new request — but users almost never retry payment attempts after 24 hours.

**Which operations need idempotency keys?**

| Operation | Needs idempotency key? |
|-----------|----------------------|
| Charge a payment card | **YES** |
| Create an order | **YES** |
| Send an email | **YES** (to avoid sending twice) |
| Debit/credit a bank account | **YES** |
| Read data (GET) | No (reads are naturally idempotent) |
| Update a user's name | Depends (PUT is naturally idempotent) |

**Rule of thumb:** Any operation with money, external side effects, or that creates something new needs idempotency keys.

---

### Part 5: Queues

#### What Is a Queue?

A **queue** is a buffer between producers (who create work) and consumers (who process work). The producer puts messages into the queue and continues immediately. The consumer reads from the queue and processes at its own pace.

```
Producer ──[message]──► QUEUE ──[message]──► Consumer
(continues immediately)         (processes when ready)
```

**Why use a queue?**

1. **Decoupling**: Producer and consumer are independent. You can change, scale, or restart either one without affecting the other.
2. **Buffering**: If the producer is faster than the consumer, the queue holds the backlog. Consumers process at their own rate.
3. **Reliability**: If the consumer crashes, messages stay in the queue. When it restarts, it resumes from where it left off.
4. **Smoothing traffic spikes**: A sudden spike in user activity creates a burst of messages in the queue. Consumers process them steadily. Your downstream systems see a smooth load, not a spike.

---

#### Queue Use Cases

| Use case | Why use a queue |
|----------|----------------|
| Sending confirmation emails | Do not block checkout; send email in the background |
| Processing uploaded images | Image resizing is slow; queue it, process asynchronously |
| Sending push notifications | Decouples notification logic from user action |
| Running analytics events | Do not slow down the main request; log events asynchronously |
| Order processing pipeline | Inventory check, payment, warehouse notification all in sequence |
| Fan-out (one event → many consumers) | One "order placed" event triggers inventory, email, analytics separately |

---

#### Queue Systems

| System | Type | Best for |
|--------|------|---------|
| **Amazon SQS** | Queue | Simple async processing, managed by AWS |
| **RabbitMQ** | Queue | Complex routing, flexible delivery |
| **Kafka** | Log (append-only) | High throughput, event streaming, replay capability |
| **Redis Lists** | Simple queue | Low latency, lightweight use cases |

**Queue vs Log:**
- A **queue** (SQS, RabbitMQ): Messages are deleted after a consumer processes them
- A **log** (Kafka): Messages are retained for a configurable period. Multiple consumer groups can read the same message. Consumers can re-read old messages.

**Use Kafka when:** You need to replay events (for debugging, reprocessing, or new consumers that need historical data), or when you have very high throughput (millions of events per second).

**Use SQS/RabbitMQ when:** You need simple, managed, fire-and-forget message delivery.

---

#### Queue Delivery Semantics

| Semantic | What it means | When to use |
|----------|--------------|-------------|
| **At-most-once** | Message may be lost, never duplicated | Metrics, analytics (losing a few events is OK) |
| **At-least-once** | Message is guaranteed to be delivered, but may be delivered more than once | Payments, orders — consumers must be idempotent |
| **Exactly-once** | Message is delivered precisely once | Extremely hard to guarantee; use at-least-once + idempotent consumers instead |

**The practical standard:** Build your consumers to be **idempotent** and use **at-least-once delivery**. This is simpler than exactly-once and still produces correct results.

---

#### Dead Letter Queue (DLQ)

When a message keeps failing to process (consumer keeps crashing, validation always fails, data is malformed), you need a place to put it so it does not block the queue forever.

A **Dead Letter Queue (DLQ)** is a separate queue for messages that have failed processing after N retries.

Benefits:
- Failed messages are isolated and do not block other messages
- Engineers can inspect DLQ messages to understand what went wrong
- Messages can be manually re-sent after fixing the bug

**Always configure a DLQ.** Alert when the DLQ has messages. A DLQ with growing messages means something is broken.

---

#### Common Queue Patterns

**Fan-out:** One event triggers multiple independent consumers.

```
"Order Placed" event
    ├──► Inventory Service (reserve stock)
    ├──► Email Service (send confirmation)
    └──► Analytics Service (record event)
```

**Competing consumers:** Multiple workers read from one queue. Each message goes to exactly one worker. Used to scale processing.

```
Queue ──► Worker 1
      ──► Worker 2   (each message goes to only one worker)
      ──► Worker 3
```

**Delay queue:** Message becomes visible only after a delay. Used for "send reminder in 1 hour" or retry with exponential backoff.

---

### Part 6: Synchronous vs Asynchronous

#### Synchronous: The Caller Waits

**Synchronous** communication means the caller sends a request and waits until it receives a response. Nothing happens until the response arrives.

```
Client sends request → [waits] → Client receives response → Client continues
```

**When to use sync:**
- The user needs the result to proceed (login, payment, showing current inventory)
- The result of this operation determines what happens next
- The operation is fast enough that waiting is acceptable

---

#### Asynchronous: The Caller Continues Immediately

**Asynchronous** communication means the caller sends a request and immediately continues. The result arrives later through a callback, webhook, polling, or event.

```
Client sends request → [continues immediately]
                              ↓ (later)
                       Client receives notification
```

**When to use async:**
- The work is slow (video transcoding, sending emails) and the user does not need to wait
- The operation is a side effect (analytics, logging) and should not slow down the main flow
- You want to decouple systems so they can scale independently

---

#### The Key Decision Framework

Ask these questions for every interaction:

1. **Does the caller need the result to proceed?** → If yes: sync
2. **Is this a side effect that should not slow down the user?** → If yes: async
3. **What happens if this fails?** → Sync: caller sees the error immediately. Async: error goes to DLQ, may be retried silently.
4. **How do I handle errors?** → Async errors are harder to surface to users. Have monitoring, DLQ alerts, and retry logic.

---

#### Practical Decision Table

| Operation | Sync or Async? | Why |
|-----------|---------------|-----|
| User logs in | **Sync** | User must see success or failure immediately |
| Payment charge | **Sync** | User must see "payment successful" or "payment declined" |
| Sending confirmation email | **Async** | User does not wait for email delivery; happens in background |
| Updating analytics | **Async** | Fire-and-forget; losing one analytics event is acceptable |
| Checking inventory before purchase | **Sync** | Must know if in stock before charging the user |
| Search indexing a new document | **Async** | Document is stored immediately; search index updates in the background |
| Sending push notification | **Async** | Background delivery; user does not wait |
| Real-time dashboard updates | **WebSocket or SSE** | Needs to be live but is not a request-response pattern |

---

#### Sync Facade Over Async Work

Sometimes you want fast user response AND slow background processing. Use a **sync facade over async work**:

1. User sends "Create order"
2. API immediately returns "Order 12345 created — processing"
3. Order ID is placed in a queue
4. Background worker processes payment, inventory, shipping
5. User can poll "GET /orders/12345" or receive a webhook when ready

The user gets an immediate response (sync). The heavy work happens asynchronously. This is how Amazon checkout works — you see "Order placed!" immediately, and the fulfillment happens in the background.

---

## 4. Mental Models

### The Toolbox Checklist

Run this checklist for **every system** you design:

```
□ Hash:        How is data distributed? Consistent hashing? What is the shard key?
□ Cache:       What is cached? Where? TTL? Invalidation strategy? What happens on cache miss?
□ State:       Are services stateless? Where does state live?
□ Idempotency: Which writes need retry safety? Are idempotency keys used?
□ Queue:       What work is async? What queue system? DLQ configured?
□ Sync/Async:  Which flows are sync (user waits)? Which are async (fire-and-forget)?
```

If you answer all six, you have covered the most common system design errors.

### The Checkout Flow (All Six Blocks Together)

A checkout is the perfect example of all six patterns:

```
User clicks "Pay"
    │
    ▼ SYNC (user waits)
[1. Idempotency check] → Is this a retry? Return stored result if so.
[2. Stateless API server] → Check session from Redis (state)
[3. Hash routing] → Route to correct inventory shard (hash)
[4. Cache check] → Is product in Redis? (cache)
[5. Charge payment] → Sync call to payment provider
[6. Create order record] → Write to database
    │
    ▼ Return "Order confirmed" to user
    │
    ▼ ASYNC (user does not wait)
[7. Queue] → Publish "OrderCreated" event
    ├──► Email worker → Send confirmation email
    ├──► Inventory worker → Reserve stock
    └──► Analytics worker → Record conversion
```

---

## 5. Real-World Example: How Netflix Uses These Patterns

**Caching:** Netflix caches movie metadata, thumbnail images, and personalized recommendation scores. The Netflix UI makes thousands of API calls per second. Without caching, this would overwhelm their databases. Cache hit rates above 95% allow the database to handle only a fraction of the actual read load.

**Queues and Async:** When a user uploads a new video (for Netflix's internal use), the processing pipeline uses queues extensively: a video is placed in a transcoding queue, workers encode it into multiple resolutions (4K, 1080p, 720p, etc.), and each result is placed in another queue for quality checking, then CDN distribution. Each stage is decoupled and can scale independently.

**Stateless services:** Netflix runs hundreds of microservices. All of them are stateless — user state is stored in external databases and caches. This allows Netflix to deploy, update, or scale any service without affecting others. A/B tests can run new versions alongside old ones without session routing complexity.

**Idempotency:** When Netflix records what you watched ("save playback position"), this is sent to their API. If the device sends duplicate updates due to network issues, the second update must not corrupt the playback history. Idempotency keys or event sequence numbers prevent duplicate writes.

---

## 6. Design Trade-offs

### When NOT to Cache

- **Financial data that must always be current**: Do not cache the account balance — serve from the database directly
- **Data that changes with every request**: Caching provides no benefit and adds complexity
- **User-specific data with poor hit rate**: If every user has unique data that is never requested twice, the cache is always missing

### When NOT to Use a Queue

- **The user needs the result immediately**: Do not put the critical path in a queue. Return the result synchronously.
- **The operation is fast**: If processing takes 5 ms, a queue adds overhead without benefit
- **You need strong ordering guarantees**: Queue ordering is complex. If strict ordering matters, design carefully.

### Sync vs Async — The Risk

**Sync risk:** If the downstream service is slow, all users wait. One slow service can back up your entire system.

**Async risk:** Errors are harder to surface to users. A background job might fail silently. If your DLQ fills up unnoticed, you lose messages.

**Solution for sync risk:** Timeouts + circuit breakers. If downstream service takes >500 ms, fail fast and return a degraded response.

**Solution for async risk:** DLQ alerts, monitoring of queue depth, retry logic with exponential backoff.

---

## 7. Common Interview Questions

1. **"How does consistent hashing work? Why is it better than modulo hashing?"**
   Expected: Explain the ring. Keys and servers are hashed to positions. Key goes to the first server clockwise. Adding/removing a server only moves ~1/N of keys. Modulo moves ~N-1/N keys when N changes — unacceptable for caches.

2. **"A celebrity posts a photo. 10 million followers try to load it in 2 seconds. What breaks?"**
   Expected: Cache stampede. The photo URL is a hot key. If the cache entry expires, all 10M requests hit the database. Solutions: TTL-based with background refresh, replicate hot keys to multiple cache nodes, serve stale while refreshing.

3. **"How do you prevent double-charging in a payment system?"**
   Expected: Idempotency keys. Client generates UUID for each payment attempt. Server checks key in store before processing. If found, return stored result. If not, process and store. Works across network retries and load-balanced requests.

4. **"When would you use a queue instead of a direct API call?"**
   Expected: When the caller does not need the result immediately, when you want to decouple producers and consumers, when you need to absorb traffic spikes, when you want retry reliability without blocking the caller.

5. **"Design the async part of a checkout flow."**
   Expected: After payment is confirmed, publish "OrderCreated" event to Kafka/SQS. Separate consumers: email service, inventory service, analytics service, shipping service. Each consumer must be idempotent (at-least-once delivery). DLQ for failed messages. Alert when DLQ has messages.

---

## 8. Key Takeaways

**Hash functions distribute data evenly.** Use consistent hashing (not modulo) for distributed caches and databases. Adding a server moves only ~1/N keys, not all of them.

**Caching is about hit rate.** A 95% cache hit rate means the database handles 20x less load. TTL balances freshness vs hit rate. Invalidation on write keeps cache consistent. Always plan for stampede.

**Stateless servers scale horizontally.** Move all state to external stores (Redis, database). Any server can then handle any request. Adding servers immediately adds capacity.

**Idempotency is mandatory for writes with side effects.** Any operation that charges money, creates records, or sends messages must accept and honor idempotency keys. Without this, retries cause duplicates.

**Queues decouple and buffer.** Use queues for work the user does not need to wait for. Always configure a DLQ. Use at-least-once delivery with idempotent consumers.

**Sync when user needs the result; async for side effects.** User-facing critical path (login, payment, checkout) = sync. Background work (email, analytics, image processing) = async.

**Run the checklist for every design:**
1. How is data distributed? (Hash)
2. What is cached, with what TTL and invalidation strategy? (Cache)
3. Where does state live? (State)
4. Which writes are retry-safe? (Idempotency)
5. What work is async and buffered? (Queue)
6. Which paths are sync and which are async? (Sync/Async)

**L5 vs L6 thinking:**
- L5: "We use Kafka for async processing."
- L6: "We publish OrderCreated events to Kafka. Email, inventory, and analytics each have a consumer group — they receive the same event independently. All consumers are idempotent (keyed by order_id). DLQ retains failed messages for 7 days with alerting. At 17,500 write QPS (our peak), Kafka handles this easily; our bottleneck is the email SMTP provider at 5,000 emails/second, so we have a separate rate-limiting layer for the email consumer."
