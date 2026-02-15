# Object Storage: Scaling and Cost

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

S3 stores over 100 *trillion* objects. How do you scale storage to hold that much? You can't have one index. One filesystem. One disk array. You need to *partition* everything. Objects distributed across thousands of machines. Metadata in a separate scalable index. Cost? Pennies per GB per month. The key: separate metadata from data, shard both. Let's design it. The architecture has two layers: metadata and data. Metadata maps keys to physical locations. Data stores the bytes. Separate concerns. Scale independently. Metadata is small, high QPS. Data is large, high throughput. Different bottlenecks. Different solutions. Metadata might use a distributed key-value store or a sharded database. Data uses a distributed file system or object store. The client speaks one API. The backend has two. Clean separation. Proven at scale. S3, GCS, Azure Blob all use this pattern. Metadata and data separation is the industry standard. Learn it. Apply it.

---

## The Story

Imagine a warehouse so big you can't walk it. You don't have one ledger. You have zones. Aisle A handles items starting with A. Aisle B handles B. Each aisle has its own ledger. Object storage scales the same way. The namespace—all possible keys—is partitioned. Each partition owns a slice. Add more partitions as you grow. No single bottleneck. No single point of failure.

---

## Another Way to See It

A library with a card catalog. The catalog doesn't hold the books—it says where each book lives. Shelf 42, Row 3. The catalog is metadata. The shelves are data. Scale the catalog by sharding it—different cards in different drawers. Scale the shelves by adding more buildings. Object storage separates metadata (fast, indexed) from data (cheap, bulk storage). Each scales independently.

---

## Connecting to Software

**Architecture:** Metadata service (maps key → physical location) + Data service (stores bytes on disks). Client PUT: metadata service assigns location, returns it; data service receives bytes, writes to disks, replicates. Client GET: metadata service returns location; data service serves bytes. Clean separation.

**Metadata sharding:** Partition by key hash. Key "photos/2024/img1.jpg" hashes to partition 7. Partition 7 owns that slice of the namespace. Each partition: its own database or table. Scale by adding partitions.

**Data placement:** Spread across racks, availability zones. Balance for durability and performance. Hot data on fast disks. Cold data on cheap disks. Tiering reduces cost.

**Cost tiers:** Hot (frequent access, higher $/GB), Warm (infrequent, cheaper), Cold/Glacier (archive, pennies—retrieval takes minutes to hours). Most data cools over time. Tiering saves millions.

---

## Let's Walk Through the Diagram

```
                    OBJECT STORAGE AT SCALE
                    
┌─────────────────────────────────────────────────────────────┐
│  METADATA SERVICE (sharded by key hash)                      │
│  Partition 0 | Partition 1 | Partition 2 | ... | Partition N │
│  key → [location, size, replicas]                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  DATA SERVICE (objects on disks, across AZs)                │
│  [Disk Pool AZ1] [Disk Pool AZ2] [Disk Pool AZ3]            │
│  Erasure-coded / Replicated                                 │
└─────────────────────────────────────────────────────────────┘
```

List operations hit metadata. Get/Put hit metadata first (for location), then data. LIST with a prefix—metadata service queries the right partition(s). Efficient. The metadata service is the brain. It must scale with the number of objects. Partition by hash of key. Each partition handles millions of keys. Add partitions as the namespace grows. The data layer is dumb: it stores bytes where it is told. Replication and erasure coding happen at the data layer. The metadata layer never touches the actual bytes—it only tracks where they live. Client uploads 1GB file. Metadata service says: write to data nodes D1, D2, D3. Client streams bytes to those nodes. Metadata stores: key, size, checksum, location. A GET: metadata returns location, client fetches from data nodes. The metadata is small—kilobytes per object. The data is large—gigabytes. Separate them. Scale them independently. Metadata: millions of QPS, low latency. Data: high throughput, batch optimizations. Different workloads. Different scaling strategies.

---

## Real-World Examples

**S3** uses a massive distributed metadata layer; storage nodes are independent. **MinIO** (self-hosted S3-compatible) shards metadata and data. **Ceph** uses CRUSH algorithm for placement. **Backblaze** publishes storage pod designs—how they pack disks for cost efficiency. The principles are universal: shard metadata, distribute data, tier for cost.

---

## Let's Think Together

**"You need to store 10 PB of video files. Estimate monthly S3 cost at $0.023/GB."**

10 PB = 10 × 1024 TB = 10,240 TB = 10,485,760 GB. At $0.023/GB: 10,485,760 × 0.023 ≈ $241,000 per month. That's Standard tier. Move to Infrequent Access ($0.0125/GB): ~$131,000. Glacier Deep Archive ($0.00099/GB): ~$10,400. Tiering matters. Most video gets cold after 30 days. Users watch new uploads. Old videos sit. Move to Infrequent Access after 30 days. Glacier after 90. S3 Lifecycle rules automate this. Set a policy. Objects transition automatically. No manual work. Cost drops dramatically. A hybrid strategy: hot for recent, cold for archive. 10 PB might cost $10K per month with aggressive tiering instead of $240K. Design for tiering from the start. A hybrid: hot for 30 days, then IA, then Glacier—dramatically lowers cost.

---

## What Could Go Wrong? (Mini Disaster Story)

You store everything in Standard tier. 100 TB. Bills climb. $2,300/month. You never thought about tiering. A year later: $27,600. Ouch. Lesson: design lifecycle policies from day one. Move old data to colder tiers automatically. S3 Lifecycle rules do this. Set and forget. Save 50–90% on storage cost.

---

## Surprising Truth / Fun Fact

S3's cheapest tier—Glacier Instant Retrieval—is still cheaper than most on-premises storage when you factor in power, cooling, and admins. The cloud didn't just scale storage—it made bulk storage so cheap that "store everything" became the default. Archive the whole company. Why not? A few hundred dollars a month.

---

## Quick Recap

- Scale: separate metadata (key → location) from data (bytes on disks); shard both.
- Metadata: partition by key hash; each partition owns a slice of namespace.
- Data: spread across racks and AZs; erasure coding or replication.
- Cost tiers: hot, warm, cold/glacier—tiering saves 50–90%.
- Lifecycle policies: auto-move old data to colder tiers; design from day one.

---

## One-Liner to Remember

*Scale object storage by sharding metadata and distributing data—tier for cost, and most data will cool over time.*

---

## Next Video

Next: notification systems. How do you notify 10 million users across email, SMS, and push? Channels, preferences, and delivery. Let's design it.
