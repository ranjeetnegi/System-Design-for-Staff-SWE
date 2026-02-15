# Database Connection Pooling in Practice

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A restaurant. Ten tables. Each meal takes an hour. Fifty people show up. Forty wait. That's terrible. But here's the thing: most of that "meal" is cooking and eating. The waiter is only busy for five minutes—take order, bring food. What if ten waiters could serve all fifty tables by quickly rotating? Table 1 done? Move to table 11. Table 2 needs the bill? Handle it. That's connection pooling. A small pool of database connections shared among many application threads. Let's see how it works.

---

## The Story

Your application handles web requests. Each request might need to talk to the database. One query. Two. Maybe five. Each query takes 10 milliseconds. The rest of the request—business logic, rendering—takes 100 milliseconds. So the connection is only "in use" for 10 ms per request. The other 90 ms it could serve another request. But if every request creates its own connection, you'd have thousands. And the database can't handle that.

PostgreSQL recommends 100–300 max connections. More than that: memory exhaustion. Context switching. The database slows. Crashes. So you have a limit. But you have 500 concurrent requests. How do 500 requests share 100 connections? Connection pooling.

---

## Another Way to See It

Think of a parking lot with 20 spaces. A thousand cars need to park today. They don't all park at once. They come, park, run their errand, leave. Twenty spaces serve a thousand cars. Turnover. Connection pooling is the same. Twenty connections serve hundreds of requests. Each request borrows a connection, uses it, returns it. Fast turnover. High utilization.

---

## Connecting to Software

**The problem:** Each DB connection = a process or thread on the database server. Memory. File descriptors. Context. 1000 connections = 1000 processes. PostgreSQL: each connection uses ~10 MB. 1000 = 10 GB. Plus context switching. The database bogs down. Crashes.

**Connection pool:** The application maintains a pool of 20 connections. 500 request threads share them. Thread needs DB: borrow connection from pool. Execute query. Return connection. Next thread borrows it. Twenty connections. Hundreds of requests. All served.

**Tools:** PgBouncer (external proxy). HikariCP (in-app, Java). Same idea: limit connections, share among many.

**Sizing:** Too few = requests queue, wait for a connection. Too many = database overwhelmed. Sweet spot: depends on query duration, request rate, DB capacity. Measure. Tune. Rule of thumb: pool size = (core count × 2) + disk count, for CPU-bound; for I/O-bound, often higher. But every workload differs. Start conservative, scale up while watching queue depth and latency.

**Connection lifecycle:** Create connection (expensive—TCP handshake, auth, allocation). Use (cheap). Return to pool. Reuse. Connections can go stale—idle too long, server closed them. Pool must detect and recreate. Health checks. "Ping before use" or "test on borrow." Libraries handle this. Configure timeouts.

---

## Let's Walk Through the Diagram

```
Without pooling:
  App threads: 500
  Each creates own connection
  DB receives: 500 connections
  DB max: 100
  Result: REJECTED. Crash. Fail.

With pooling (20 connections):
  App threads: 500
  Pool: 20 connections
  Thread 1 borrows conn 1 -> query -> return
  Thread 2 borrows conn 1 -> query -> return
  ...
  DB receives: 20 connections
  Result: OK. Fast. Stable.

  [App Server]          [Pool]         [Database]
  Thread 1 ----\
  Thread 2 -----+-> [20 conns] --> [100 max] OK
  Thread 3 ----/
  ...
  Thread 500 --/
```

---

## Real-World Examples (2-3)

**Rails/Django:** Built-in pooling. Each app process has a pool. Default 5–20 connections per process. Scale horizontally = more processes = more pools. Watch total connections to DB.

**PgBouncer:** Sits between app and PostgreSQL. App opens 1000 "connections" to PgBouncer. PgBouncer maintains 50 real connections to PostgreSQL. Translates. Queues. Life-saver for connection-heavy apps.

**Serverless (Lambda):** Each invocation might create a connection. Cold start. Thousands of invocations = connection explosion. Solution: connection pooling as a service (RDS Proxy) or reuse connections across invocations in a warm instance. RDS Proxy sits between Lambdas and RDS. Pools connections. Lambdas "connect" to the proxy; proxy maintains a small pool to the actual database. Handles the scale mismatch.

**Kubernetes + apps:** Each pod has its own pool. 10 pods × 20 connections = 200. Scale to 50 pods = 1000 connections. Watch the total. Use a service like PgBouncer as a sidecar or shared deployment to pool at the proxy level. Reduces total connection count to the database.

---

## Let's Think Together

**Question:** You have 10 app servers. Each has a pool of 20 connections. Total connections to DB = 200. Database max connections = 100. What happens?

**Answer:** Trouble. 200 > 100. The database will reject connections once it hits 100. Some requests will fail with "too many connections" or time out. User-facing errors. Cascading failures. Fix: reduce pool size per server. 10 servers × 10 connections = 100. Or use PgBouncer—each server talks to a local PgBouncer, which maintains a smaller pool to the real DB. Total: under 100. Plan for total connections = (app servers × pool size) and keep it under the DB limit with headroom for maintenance connections.

---

## What Could Go Wrong? (Mini Disaster Story)

Pool size 5 per server. 20 servers. Load spikes. Every request needs DB. Five connections per server = 100 connections. But each request holds the connection for 200 ms (slow query). Request rate: 1000/sec. 1000 × 0.2 = 200 "connection-seconds" per second. You need 200 concurrent connections. You have 100. Queue grows. Latency spikes. 5 seconds. 10 seconds. Users see timeouts. The lesson: pool size and query duration matter. Slow queries = connections held longer = need more connections or fix the queries.

---

## Surprising Truth / Fun Fact

Connection poolers can do more than pool. PgBouncer has "transaction mode"—connection is returned to pool after each transaction, not each query. One connection can serve many short transactions from different clients. Connection churn drops. Throughput rises. Pooling isn't just about limiting—it's about efficient reuse.

---

## Quick Recap (5 bullets)

- **Problem** = too many connections overwhelm DB; PostgreSQL likes 100–300 max
- **Pool** = small set of connections shared by many threads; borrow, use, return
- **Tools** = PgBouncer, HikariCP—manage the pool between app and DB
- **Sizing** = too few = queue; too many = overwhelm; tune by workload
- **Total** = sum of all pools across servers must stay under DB limit

---

## One-Liner to Remember

**Connection pooling: few connections, many requesters—borrow, use, return—so the database never drowns in connections.**

---

## Next Video

Up next: When to use NewSQL. Spanner, CockroachDB—distributed SQL that scales. What's the catch?
