# Object Storage: Durability and API

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You give a precious photo to a storage company. They promise: "We will NEVER lose it. Even if our warehouse burns down." How? They make copies. Three copies in different buildings. Different cities. Even if two buildings collapse, the third has your photo. That's how S3 achieves 11 nines of durability—99.999999999%. Let's design object storage together.

---

## The Story

Object storage is different from file storage. No hierarchy of folders that act like a filesystem. Instead: buckets and keys. A bucket is a namespace. A key is the object's address. Like "photos/vacation/beach.jpg." You PUT the data. You GET it back. You don't mount it like a disk. You access it over HTTP. Simple. And behind that simplicity: replication, erasure coding, and geographic spread—so your data survives almost anything.

---

## Another Way to See It

A safety deposit box system. You don't have one box. The bank keeps your valuables in multiple vaults. If one vault is compromised, the others hold copies. Object storage does that at scale: your bytes are replicated across availability zones, sometimes across regions. The API is simple—put, get, delete—but the durability machinery under the hood is sophisticated.

---

## Connecting to Software

**Durability** = probability that data is NOT lost. 11 nines = 0.000000001% annual loss rate. For 10 billion objects, you might lose one per year. How? **Replication:** Store copies across multiple Availability Zones—physically separate data centers. **Erasure coding:** Store data as coded fragments across many disks. Reconstruct from a subset. Survive multiple disk and even node failures.

**API:** PUT /bucket/key (upload), GET /bucket/key (download), DELETE /bucket/key, LIST /bucket?prefix=photos/ (list objects). Each object has: key, data, metadata (content-type, custom headers), ACL (who can access). No partial updates—replace the whole object. That simplicity enables durability. No random writes. No partial updates. Replace the whole object. That makes replication predictable. Write to three zones. Wait for confirmations. Return success. The client gets 200 only when data is safe. Sync replication. No ambiguity. The client never gets a false success. If replication fails, the write fails. Retry. The system prefers correctness over availability for writes. For reads, if one replica is down, read from another. Durability and availability are different. Design for both. Durability: will my data survive? Availability: can I access it now? S3 offers both. Multi-AZ replication gives durability. Multiple replicas per AZ give availability. A disk failure does not cause data loss—replicas. A zone outage does not cause unavailability—other zones serve. The client sees a simple API. The backend is a distributed system. Erasure coding: instead of 3 full copies, store N data fragments + M parity. Reconstruct from any N of N+M. Survive M failures. More efficient than full replication. Same durability. Used by many large-scale storage systems. Append? Use a new key or multipart upload for large files.

---

## Let's Walk Through the Diagram

```
                    OBJECT STORAGE LAYERS
                    
┌─────────────────────────────────────────────────────────┐
│  API Layer: PUT, GET, DELETE, LIST                       │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────┐
│  Metadata: key, size, content-type, custom headers       │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────┐
│  Durability Layer:                                       │
│  AZ1 ──► Copy 1    AZ2 ──► Copy 2    AZ3 ──► Copy 3      │
│  (or erasure-coded fragments across many nodes)          │
└─────────────────────────────────────────────────────────┘
```

Write arrives. System replicates to multiple AZs. Only after replication is confirmed does it return success. That's synchronous replication for the critical path—your write isn't "done" until durability is guaranteed.

---

## Real-World Examples

**Amazon S3** offers 11 nines durability, cross-AZ replication by default. **Google Cloud Storage** and **Azure Blob** offer similar guarantees. **Backblaze B2** and **Wasabi** provide S3-compatible APIs at lower cost with strong durability. The API is becoming a standard—S3-compatible is the lingua franca of object storage. MinIO, Backblaze B2, Wasabi, Cloudflare R2—all speak S3. Write your application once, run it anywhere. Portability matters. Durability is table stakes. The differentiator is cost, performance, and features like versioning and lifecycle policies.

---

## Let's Think Together

**"How does S3 handle a write and simultaneously ensure 3 replicas? Synchronous or async?"**

Synchronous from the client's perspective. You PUT, you get 200 when the data is durably stored. Internally: the write goes to multiple nodes. All must acknowledge before success is returned. So it's synchronous replication—your write blocks until replicas confirm. The alternative (async) would return success before replication; faster but you'd lose durability if the primary failed before replicating. S3 chooses durability. Latency is a few milliseconds longer; worth it for "your data never gets lost."

---

## What Could Go Wrong? (Mini Disaster Story)

A bug in your application. You DELETE a bucket. Or overwrite a key with empty data. The storage system didn't lose it. You did. Object storage guarantees durability against hardware failures—not against user error. Solution: versioning. Keep previous versions. Soft delete. Backup to another bucket or region. Durability is one layer; human mistakes need another.

---

## Surprising Truth / Fun Fact

S3 launched in 2006. One of the first true "cloud" storage services. Before that, you bought servers and disks. S3 said: store objects, pay per GB, infinite scale. It changed how we build. Netflix, Airbnb, countless startups—their photos, videos, backups—live on S3. Over 100 trillion objects stored. And the core API hasn't changed. PUT, GET, DELETE. Simple. Lasting.

---

## Quick Recap

- Durability: 11 nines = replicate across AZs; erasure coding for extra safety.
- API: PUT, GET, DELETE, LIST; key-based, no filesystem hierarchy.
- Metadata: content-type, custom headers, ACL per object.
- Replication: synchronous—write succeeds only after replicas confirm.
- Protect against human error: versioning, soft delete, backups. Durability protects against hardware. You protect against mistakes. Enable versioning on critical buckets. Keep 30 days of versions. Or more. MFA delete for production buckets. Cross-region replication for disaster recovery. Object lock for compliance. The tools exist. Use them. Object storage vendors have thought through durability and compliance. Your job is to configure it correctly. Versioning, replication, lifecycle policies. Enable what your use case needs. Review periodically. Durability is not set-and-forget; it is configured-and-verified. Run periodic restore tests. Ensure backups work. Verify replication. Trust but verify. Cost is small compared to the cost of data loss.

---

## One-Liner to Remember

*Object storage: put and get by key, durability through replication—11 nines means your data survives almost everything.*

---

## Next Video

Next: how does object storage scale to 100 trillion objects? Metadata, sharding, and cost tiers. Let's go.
