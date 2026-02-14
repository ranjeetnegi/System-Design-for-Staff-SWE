# Change Data Capture (CDC): What and Why

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A spy camera on a document. Every time someone changes it—adds a word, deletes a sentence—the camera captures the change. Sends it to headquarters. Headquarters knows exactly what changed. When. Without asking for the full document. That's CDC. Your database. Every change. Captured. Streamed. Automatically.

---

## The Story

Imagine a spy camera on a document. Every time someone changes it—adds a word, deletes a sentence, rewrites a paragraph—the camera captures the change. Sends it to headquarters. Headquarters now knows exactly what changed. When. Who. Without requesting the full document. Without polling "what's new?" The changes flow. Automatically. Push. Not pull. CDC—Change Data Capture—is that for your database. A system that watches your database for changes. Every INSERT. Every UPDATE. Every DELETE. Captured as an event. Streamed to Kafka or another system. Downstream services react. Search index updates. Cache invalidates. Data warehouse syncs. No polling. No "SELECT * WHERE updated_at > last_check." No load on your app. No cron jobs. The changes come to you. The database writes. CDC reads the write-ahead log. Publishes. Subscribers consume. Clean. Efficient. Real-time. This is how modern data pipelines work. At scale.

---

## Another Way to See It

Think of a security camera at a store. It doesn't ask "what happened today?" every hour. It records. Continuously. When something happens, it's there. CDC is like that. Your database does its job. Writes. CDC watches the write-ahead log. Every change. Records it. Streams it. No interrupting the database. No extra queries. Just observe. And flow.

---

## Connecting to Software

**How it works:** Every database has a write-ahead log (WAL) or binlog. When you INSERT, UPDATE, DELETE, the database writes to this log first. For durability. Before applying to tables. CDC reads this log. Doesn't query your tables. Doesn't add load. Doesn't require schema changes. Just reads the log. Every change becomes an event. "Row X in table orders: INSERT. Values: ..." Published to Kafka. Or another system. Downstream consumes. Reacts. The beauty: your application doesn't change. You write to the database. As normal. CDC is a tap. Observing. Not interfering. Zero impact on write path. High value on read path. That's why teams love it.

**Use cases:** (1) **Search index sync.** Update product in PostgreSQL. Elasticsearch must know. CDC captures the change. Publishes. Search index consumes. Updates. No polling. No cron. No "SELECT * WHERE updated_at > X." Real-time. (2) **Data warehouse.** Replicate DB to Snowflake. BigQuery. CDC streams changes. Warehouse updates. Near real-time. ETL becomes ELT. Extract from WAL. Load. Transform in warehouse. Simpler pipeline. (3) **Cache invalidation.** DB change. Cache stale. CDC event: "this key changed." Invalidate. Or update. No TTL guessing. Precise. (4) **Event-driven systems.** DB is source of truth. CDC makes it event source. Microservices react. SAGAs. Notifications. All from DB changes. No dual-write. Single source. CDC fans out. Clean architecture. One write. Many readers.

---

## Let's Walk Through the Diagram

```
    CDC FLOW

    [App] ---- INSERT/UPDATE -------> [PostgreSQL]
                                            |
                                            | WAL / binlog
                                            v
                                    [CDC Connector]
                                    (Debezium, etc.)
                                            |
                                            | change events
                                            v
                                        [Kafka]
                                            |
                    +-----------------------+-----------------------+
                    |                       |                       |
                    v                       v                       v
              [Elasticsearch]         [Cache]              [Data Warehouse]
              update search          invalidate            replicate
```

App writes. DB writes. CDC reads WAL. Publishes. Many consumers. Search. Cache. Analytics. All in sync. No polling.

---

## Real-World Examples (2-3)

**Example 1: E-commerce search.** Product table in PostgreSQL. Admin updates price. Without CDC: cron job polls every 5 minutes. Stale index. With CDC: Debezium captures change. Kafka. Elasticsearch consumer updates. Search index fresh. Seconds. Not minutes.

**Example 2: Multi-tenant sync.** Primary DB. Replica in another region. CDC streams changes. Replica applies. Or: same data to analytics DB. Different schema. CDC transforms. Publishes. Analytics stays current.

**Example 3: Outbox pattern.** Outbox table in DB. CDC reads. Publishes outbox rows to Kafka. No poller. No relay process. Debezium IS the relay. Simpler. Reliable. CDC + outbox = clean architecture.

---

## Let's Think Together

**You update a product price in PostgreSQL. How does Elasticsearch know? Polling every second? Or CDC?**

Polling: SELECT * FROM products WHERE updated_at > last_check. Every second. Load on DB. Delay. Miss rapid changes. CDC: database writes to WAL. Debezium reads. Publishes change event. Elasticsearch consumes. Updates. No poll. Low load. Real-time. CDC wins. For sync problems, CDC is the modern answer. Polling is the old way.

---

## What Could Go Wrong? (Mini Disaster Story)

A team set up CDC. Forgot that the connector needs to track position. Connector crashed. Restarted. Started from "now." Missed hours of changes. Search index stale. Warehouse missing data. Lesson: CDC connectors must checkpoint. Store offset. "I've processed up to LSN 12345." Restart? Resume. Debezium does this. But configure retention. Don't lose position. Monitor lag. CDC is powerful. Misconfigured? Data loss.

---

## Surprising Truth / Fun Fact

Debezium captures from MySQL, PostgreSQL, MongoDB, SQL Server, and more. One project. Many databases. Open source. Red Hat. Netflix uses CDC extensively for their data pipeline. Uber. Airbnb. LinkedIn. Database changes flow to their event bus. Downstream: recommendations, analytics, operational systems, search indexes. CDC is not niche. It's infrastructure. When you outgrow polling. When you need real-time. When you have multiple consumers of database state. CDC is the answer. Learn it. Use it. It'll transform how you think about data flow.

---

## Quick Recap (5 bullets)

- **CDC** = capture database changes from WAL/binlog. Stream as events. No polling.
- **How:** Read transaction log. INSERT/UPDATE/DELETE → events → Kafka.
- **Use cases:** Search sync, warehouse replicate, cache invalidate, event-driven.
- **Tools:** Debezium (popular, open-source), Maxwell, AWS DMS.
- **Outbox + CDC:** Outbox table. CDC publishes. No relay process. Clean.

---

## One-Liner to Remember

**CDC: Your database changes. CDC watches. Streams. Downstream reacts. No polling. Just flow.**

---

## Next Video

That's our journey through distributed transactions, SAGAs, outbox, delivery semantics, queues, logs, streams, and CDC. The foundations of event-driven systems. What topic should we cover next? Let us know in the comments. See you there.
