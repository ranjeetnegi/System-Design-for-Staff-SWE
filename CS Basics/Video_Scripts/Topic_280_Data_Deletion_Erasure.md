# Data Deletion and Right to Erasure: When "Delete" Isn't Simple

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You break up with someone. "Delete all my photos from your phone!" they say. You open the gallery. You delete. Done, right? Wrong. Backup on iCloud? Still there. Shared album with friends? Still there. Photo sent to the group chat? Still there. Printed copy in a drawer? Still there. TRUE deletion is hard. In software, when a user says "delete everything about me," that data might live in 15 databases, 3 caches, 5 backups, and 10 downstream services. GDPR's right to erasure means you have to find it ALL. Let's see how.

---

## The Story

GDPR Article 17—the right to erasure, or "right to be forgotten"—says: when a user requests deletion, you must delete their personal data from ALL systems. Not just the main database. Every replica. Every backup. Every cache. Every log that might contain their data. Every analytics pipeline. Every third-party service you've shared data with. Everywhere.

Think of it like a house with secret drawers. The user says "remove everything that's mine." You clear the living room. But there's a drawer in the kitchen. A box in the attic. A safe in the basement. Data in software is the same. It's in the primary database. It's in read replicas. It's in Redis cache. It's in Elasticsearch for search. It's in S3 backups. It's in Kafka logs. It's in the data warehouse. It's in the CRM you synced to. Each place is a drawer. You have to open every one.

---

## Another Way to See It

Imagine you wrote your diary on sticky notes and distributed them to 20 friends. "Delete my diary," you say later. You have to contact every friend. Get every note back. Shred them. One friend lost theirs—it's in a landfill. Another made a photocopy. Deletion across a distributed system is that hard. Data replicates. It spreads. True erasure means tracing every copy.

---

## Connecting to Software

**Soft delete vs hard delete:** Soft delete means you mark a record as deleted—set a flag, filter it from queries. The data is still on disk. It's "logically" gone. GDPR eventually requires hard delete—physical removal. Soft delete is a step. It helps you "hide" quickly. But for full compliance, you need to purge. Schedule hard deletes. Remove from backups where possible.

**The backup problem:** you can't easily remove one user's record from a 50GB backup tape. Backups are snapshots. Restoring, modifying, and re-backing up is expensive. One solution: **crypto-shredding**. Encrypt each user's data with a unique key per user. To "delete" a user: destroy their key. The data is still on disk—but it's ciphertext. Unreadable. Effectively gone. No need to rewrite backups. The key destruction propagates. Elegant.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│              USER DATA: WHERE IT LIVES (and must be deleted)              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   User Request: "Delete all my data"                                     │
│                                                                          │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   │
│   │ MySQL   │   │ Redis   │   │Elastic- │   │ S3      │   │ Kafka   │   │
│   │ Primary │   │ Cache   │   │ search  │   │ Backups │   │ Logs    │   │
│   └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘   │
│        │             │             │             │             │        │
│        │  Hard       │  Invalidate │  Delete     │  Crypto-    │  Expire │
│        │  delete     │  / evict    │  by ID      │  shred or   │  (time) │
│        │             │             │             │  overwrite  │         │
│        ▼             ▼             ▼             ▼             ▼        │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  Deletion service: fan-out to ALL systems. Audit: verify gone.    │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│   Replicas, read replicas, data warehouse, analytics, 3rd parties too.  │
└─────────────────────────────────────────────────────────────────────────┘
```

Every box must be addressed. Miss one = compliance failure.

---

## Real-World Examples

**Google** allows users to request deletion of their data. They have a documented process. Data in Search, Gmail, Drive, Ads—each has its own flow. They also retain some data for legal or operational reasons (with disclosure). Complexity is real.

**A fintech** encrypts each customer's records with a per-customer key in KMS. When a customer requests deletion, they delete the KMS key. The encrypted blobs in S3 and RDS become unreadable. No need to touch backups. Crypto-shredding in action.

**A social app** had user data in MySQL, Redis, Elasticsearch, and Snowflake. Deletion was manual. Engineers would run scripts in each system. Sometimes they forgot Elasticsearch. Audit found 200 "deleted" users whose search indices still had data. They built a central deletion service that fans out to all systems and verifies.

---

## Let's Think Together

**"User requests deletion. Their data is in: MySQL, Redis cache, Elasticsearch, S3 backups, Kafka logs. How do you delete from all?"**

Answer: Orchestrate. (1) MySQL: hard delete the rows (or soft delete first, then batch hard delete). (2) Redis: delete keys for that user, or invalidate cache entries. (3) Elasticsearch: delete by user ID in the index. (4) S3 backups: tricky. Option A: wait for backup retention to expire (if compliant with timing). Option B: crypto-shred—if data was encrypted per-user, destroy the key; backups become unreadable. Option C: recreate backups without that user (expensive). (5) Kafka: logs have retention. After retention, data is gone. For active logs, you can't easily delete one user's messages. Document the retention window. Ensure no long-term storage of PII in Kafka. The key: a central deletion workflow that hits every system and logs success/failure. Audit the audit.

---

## What Could Go Wrong? (Mini Disaster Story)

A company implemented "delete user" by soft-deleting in the main database. The UI stopped showing the user. They thought they were compliant. A year later, a GDPR audit. The auditors asked: "What about the data warehouse? The analytics events? The CRM sync?" The company had never deleted from those. Thousands of "deleted" users still had data in Snowflake, Amplitude, and Salesforce. Fines. Reputation damage. They built a proper deletion pipeline—but only after getting caught. Deletion must be comprehensive from day one.

---

## Surprising Truth / Fun Fact

Some data can't be deleted even under GDPR. Legal obligations—tax records, litigation holds—override the right to erasure. The regulation allows exceptions. But you must document them. "We retain X for Y years because of Z." Don't assume you can delete everything. Know the lawful bases for retention. And when you can delete, delete everywhere.

---

## Quick Recap (5 bullets)

- **Right to erasure (GDPR Art. 17):** user can request deletion; you must delete from ALL systems.
- **Scope:** primary DB, replicas, caches, search indices, backups, logs, analytics, third parties.
- **Soft delete:** mark as deleted, filter from queries—helps quickly; eventual hard delete needed for full compliance.
- **Backups:** hard to modify. Crypto-shredding (encrypt per-user, destroy key) makes data unreadable without touching backups.
- **Process:** central deletion service, fan-out to all systems, verify, audit. Document what you delete and when.

---

## One-Liner to Remember

*"Deleting from one database is easy. Deleting from everywhere is the real right to erasure."*

---

## Next Video

Up next: **Kafka: Topic, Partition, Offset**—the newspaper with sections, pages, and page numbers. We'll map Kafka's core concepts to a simple mental model and see how events get organized.
