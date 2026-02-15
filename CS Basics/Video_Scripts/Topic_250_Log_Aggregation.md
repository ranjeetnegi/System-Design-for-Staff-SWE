# Log Aggregation: Tiering and Compression

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

1,000 servers. Each generates 1 GB of logs per day. That's 1 TB per day. 30 TB per month. 365 TB per year. You can't keep all of it on fast SSDs. You can't search all of it in real-time. Solution: tier it. Last 24 hours: hot storage. Fast. Searchable. Last 30 days: warm. Cheaper. Slower. Older: cold. S3 Glacier. Compressed. Archived. Search when needed. Not always indexed. Let's see how.

---

## The Story

Logs are the memory of your system. What happened. When. Why. Debugging. Auditing. Compliance. You need them. But raw logs are massive. Every request. Every error. Every debug line. Terabytes per day. At scale. Store everything on expensive fast storage? Bankruptcy. Store nothing? Blind. The answer: tiering. Hot: last 7 days. Indexed. Full-text search. Elasticsearch, OpenSearch. Fast queries. Expensive. Warm: 7-30 days. Compressed. Slower queries. Cheaper storage. Cold: 30+ days. Archived. S3 Glacier. Restore when needed. May take hours. But you have it. Compliance. Rare investigations. Cost drops dramatically. 1 TB hot might cost $100/month. 1 TB cold might cost $4. Same data. Different tier. Different cost. Design for the access pattern. Most queries: last 24 hours. Optimize for that. Older data: keep it. Don't optimize for it. Tier. Compress. Archive.

---

## Another Way to See It

Think of a library. Active section: bestsellers. On the main floor. Easy access. Warm section: recent acquisitions. In the stacks. Get it in 5 minutes. Archives: rare books. In the basement. Request. Wait a day. Retrieve. Same concept. Logs. Hot = main floor. Warm = stacks. Cold = basement. You don't put every book on the main floor. You don't put every log in Elasticsearch. Tier by access frequency. Design for how you actually use the data. Not how you might use it. Rarely do you need to search 6-month-old logs in 100ms. Accept 10 minutes. Save millions.

---

## Connecting to Software

**Ingestion pipeline.** Agents on each server: Filebeat, Fluentd, Datadog agent. They tail log files. Ship to collector. Logstash, Vector, Fluent Bit. Collector parses, enriches, routes. Sends to queue: Kafka, Kinesis. Decouples producers from consumers. Burst of logs? Queue absorbs. Consumers: indexers. Elasticsearch, OpenSearch. Write to hot tier. Or: bypass for cold. Route old logs directly to S3. Don't index. Just store. Compression: gzip, zstd. 5-10x compression ratio typical. 1 TB raw → 150 GB compressed. Massive savings. Apply compression before cold storage. Always.

**Tiering.** Hot: 1-7 days. Full index. Full-text search. Sub-second queries. Elasticsearch. Replicas for durability. Expensive. Warm: 7-30 days. Index exists but no replicas. Or: compressed segments. Slower read. Cheaper. Cold: 30+ days. No index. Raw or compressed files in object storage. S3. Glacier. Restore: request retrieval. 1-5 hours for Glacier. Then search. Or: re-index into temporary Elasticsearch. Query. Delete when done. Pay for compute when you need it. Not 24/7.

**Retention.** Policy: hot 7 days, warm 30 days, cold 1 year. Or 7 years for compliance. Automate. Lifecycle management. Curator for Elasticsearch. S3 lifecycle rules. Move to Glacier after 90 days. Delete after 7 years. Set it. Forget it. Until you need to change it. Retention is a policy decision. Cost vs compliance vs debuggability. Balance. Document. Enforce.

---

## Let's Walk Through the Diagram

```
LOG AGGREGATION - TIERING
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   SERVERS (1000s)                                                 │
│   Filebeat, Fluentd ──► Kafka ──► Elasticsearch (HOT)            │
│        │                              │ 1-7 days, indexed        │
│        │                              │ Fast. Expensive.         │
│        │                              ▼                          │
│        │                         WARM (7-30 days)                │
│        │                         Compressed. Slower. Cheaper.   │
│        │                              │                          │
│        └─────────────────────────────┼──► S3 / Glacier (COLD)   │
│                                      │ 30+ days. Archived.       │
│                                      │ Restore when needed.      │
│                                                                  │
│   COMPRESSION: zstd/gzip. 1TB raw → 150GB. 5-10x ratio.          │
│   RETENTION: Policy-driven. Lifecycle automation.               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Logs flow from servers. Agents ship. Kafka buffers. Hot: Elasticsearch. Indexed. Fast search. 7 days. Then: move to warm. Compress. Cheaper. 30 days. Then: cold. S3 Glacier. Archived. Restore when needed. Compression at each stage. Raw to compressed. Storage cost drops. The diagram shows the flow. Hot for now. Warm for recent. Cold for compliance. Tier. Compress. Retain. The recipe for log storage at scale. Without going broke.

---

## Real-World Examples (2-3)

**Elasticsearch + Curator.** Hot indices. Curator rotates: close old indices, shrink, move to warm storage. Delete or archive to S3. Standard pattern. Open source. Many companies run this. Proven. The stack is mature.

**Datadog / Sumo Logic / Splunk.** Managed. They handle tiering. You send logs. They store. Query. You pay. Simpler. More expensive at scale. Trade money for ops. When logs are critical, managed can make sense. When cost matters, self-host with tiering.

**AWS.** CloudWatch Logs. S3 export. Glacier for archive. Native tiering. Integrated. If you're on AWS, this is the path. Or: OpenSearch (fork of Elasticsearch). Managed. Lifecycle policies. Tier to S3. Cold storage. The cloud providers have solved this. Use them or learn from them.

---

## Let's Think Together

**"Alert fires at 2 AM. You need to check logs from 3 months ago. They're in cold storage. How long until you can search them?"**

Cold = Glacier or similar. Restore: initiate retrieval. Standard Glacier: 3-5 hours. Expedited: 1-5 minutes (expensive). So: 3-5 hours typical. Then: logs are in S3. Not indexed. To search: load into Elasticsearch. Or use a tool that scans S3. Athena. Scan compressed files. Minutes to hours depending on volume. Or: re-index. Spin up temporary Elasticsearch. Ingest from S3. Query. Could take 1-2 hours for 1 TB. Total: 4-7 hours from "I need it" to "I'm searching." That's the cold storage tradeoff. Mitigation: for critical investigations, keep more in warm. 90 days warm instead of 30. Cost more. Access faster. Or: accept the delay. Most investigations are recent. Cold is for rare. Compliance. Audits. Design for the common case. Optimize hot. Accept cold delay when it happens. Document the process. Run a drill. "We need 3-month-old logs." How do we get them? Practice. Once. So when it matters, you know.

---

## What Could Go Wrong? (Mini Disaster Story)

A company. All logs in Elasticsearch. No tiering. 90 days retention. Growth. 10 TB in the cluster. Queries slow. Cluster unstable. OOM. They needed to tier. But: no process. How do you move data out of Elasticsearch? Curator. Shrink. Close. But they'd never done it. No runbooks. Panic. Add more nodes. Temporary relief. Cost 3x. Finally: implemented tiering. Warm. Cold. Curator. Lifecycle. Took 3 months. During that time: constant fires. Cluster crashes. Lost logs. Postmortem: "We should have tiered from the start." Yes. Design for growth. Tier from day one. Even if your volume is small now. The migration is painful. Building it in? Much easier. Learn from their pain. Tier early. Compress. Retain intelligently. Your future self will thank you. Your budget will too.

---

## Surprising Truth / Fun Fact

zstd compression—developed by Facebook—often achieves 10x compression on log data. Logs are repetitive. Timestamps. Structure. "ERROR", "WARN", "request_id=". zstd exploits that. 1 TB raw logs → 100 GB compressed. Or better. Compare to gzip: maybe 5x. zstd is faster to compress and decompress too. Modern default. Use it. When you're storing 365 TB per year, 10x compression saves 90% of storage cost. That's real money. Millions at scale. Compression isn't optional. It's survival.

---

## Quick Recap (5 bullets)

- **Tiering:** Hot (1-7 days, indexed, fast) → Warm (7-30 days, compressed) → Cold (30+ days, archived).
- **Ingestion:** Agents → Kafka → Indexer. Decouple. Buffer. Scale.
- **Compression:** zstd or gzip. 5-10x ratio. 1 TB → 150 GB. Massive savings.
- **Retention:** Policy-driven. Hot 7, warm 30, cold 1 year. Lifecycle automation.
- **Cold restore:** Glacier: 3-5 hours. Then re-index or scan. Design for it. Drill it.

---

## One-Liner to Remember

**Log tiering is a library—main floor for what you need now, basement for what you might need someday, and compression makes the basement fit.**

---

## Next Video

Next: we'll dive deeper into observability, tracing, and connecting metrics, logs, and traces for full visibility.
