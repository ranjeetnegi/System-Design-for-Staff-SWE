# Block vs File vs Object Storage

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You need to store stuff. A raw empty room. A filing cabinet. Or a massive warehouse with a guy who hands you a ticket.

Three completely different approaches. Three completely different mindsets. And in the cloud—three storage types that power everything from your database to your Instagram photos.

Let's see which one fits what.

---

## The Story

Picture three ways to store things at home.

**Method 1 — Block:** You get a raw empty room. Floor space measured in square meters. That's it. No shelves, no labels. You decide how to use it. Put a bed, a desk, a treadmill—whatever. Maximum control. Maximum speed. You organize everything yourself. This is block storage. Raw bytes. No file system on top. Just chunks of data you manage.

**Method 2 — File:** You get a filing cabinet. Folders inside folders. `/home/photos/vacation/beach.jpg`. You navigate by path. Organized. Hierarchical. You know exactly where everything lives. This is file storage. Like your computer's file system. Paths, permissions, directories.

**Method 3 — Object:** You bring a box to a massive warehouse. They take it. They give you a receipt: "box-2024-07-abc123." Want it back? Show the ticket. They fetch it. No folders. No hierarchy. Just millions of boxes with unique keys. This is object storage. One key per object. Flat. Simple. Massive scale.

Each approach solves a different problem. Raw control. Organized hierarchy. Infinite scale with a receipt.

But here's where things get interesting. Try using the filing cabinet like the raw room—no structure, just dump stuff in. Chaos. Or try using the warehouse like a filing cabinet—"I need the box in Folder A, Subfolder B." The warehouse guy shrugs. "We don't have folders. Give me the ticket." Right tool. Right mindset.

---

## Another Way to See It

Think of it like shipping.

Block storage is like renting warehouse space. You get square footage. You bring your own shelves, your own system. You own the layout. Fast and flexible. But you do all the work.

File storage is like a post office with P.O. boxes. Addresses. Paths. You go to Box 123, Floor 4, Building A. Everyone follows the same structure.

Object storage is like a parcel service. You hand over a package. You get a tracking number. You don't care where they put it. You just give them the number when you want it back.

Same goal—storing things—but three very different mental models.

---

## Connecting to Software

**Block storage** is raw. The lowest level. Databases and virtual machines use it. Why? Because they need to control exactly how data is laid out on disk. They build their own structures on top. Amazon EBS, Google Persistent Disk—these are block storage. Fastest. Lowest latency. But no built-in file system. Your application manages the blocks.

**File storage** gives you hierarchy. Paths like `/data/projects/report.pdf`. POSIX permissions. Shared access. Multiple servers can mount the same NFS share. Perfect for home directories, shared documents, anything that needs "folders." Amazon EFS, NFS, CIFS—file storage.

**Object storage** is flat. Key-value at massive scale. You upload a blob. You get a key. You retrieve by key. No directories—though keys can LOOK like paths: `photos/2024/beach.jpg` is just a string. Amazon S3, Google Cloud Storage, Azure Blob. Cheapest per gigabyte. Most scalable. But higher latency than block or file.

When do you pick which? Block for databases and VMs—they need raw speed and control. File for shared documents, home directories, anything with a folder structure. Object for images, videos, backups, logs—anything that scales to billions and doesn't need a hierarchy.

---

## Let's Walk Through the Diagram

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  BLOCK STORAGE  │  │  FILE STORAGE   │  │ OBJECT STORAGE  │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│                 │  │                 │  │                 │
│  Raw blocks     │  │  /home/user/    │  │  bucket/key     │
│  [block 0][1][2]│  │    docs/        │  │  "photo.jpg"    │
│  You organize   │  │    report.pdf   │  │  → object       │
│                 │  │                 │  │                 │
│  DBs, VMs       │  │  NFS, EFS       │  │  S3, GCS        │
│  Fastest        │  │  Shared access  │  │  Cheapest       │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Block:** Raw chunks. Your app says "write to block 47." No meaning. No path. Pure bytes.

**File:** Tree structure. Navigate. Open. Read. Standard file operations.

**Object:** Flat namespace. PUT with key. GET with key. That's it. Billions of keys. No hierarchy.

---

## Real-World Examples (2-3)

**Example 1 — Instagram:** Billions of photos. Each photo is an object. Key could be `user123/2024/07/photo_abc.jpg`. Stored in object storage (S3-style). Metadata (likes, comments, user) lives in a database. The actual image bytes? Object storage. Cheap. Durable. Scalable.

**Example 2 — Netflix:** Video files? Object storage. Hundreds of petabytes. Thumbnails, metadata? Databases. Block storage runs the databases and VMs that power their control plane.

**Example 3 — Your laptop:** The SSD is block storage. The operating system builds a file system on top—that's file storage. When you sync to iCloud or Dropbox, your files often land in object storage on the backend.

---

## Let's Think Together

Instagram stores billions of photos. Block, file, or object storage? Why?

Pause and think.

If you said object storage—you're right. Photos are large blobs. Rarely edited in place. Need to scale to billions. Cheap storage matters. Object storage wins. Block would be overkill and expensive. File storage doesn't scale to that level of flat, key-based access at that size.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup built their app on block storage. Every user upload, every image, every video—stored as raw blocks. Control felt great. Performance was amazing. Then they hit 10 million users. Storage costs exploded. Block storage is expensive per GB. They had no metadata layer—finding "John's profile photo" meant scanning blocks. Backup took days. One wrong block write and data corrupted. They had to migrate to object storage. Months of work. Right tool matters from the start.

---

## Surprising Truth / Fun Fact

Amazon S3 stores over 100 trillion objects. One hundred trillion. Object storage is the backbone of the cloud. Most of the data you touch online—photos, videos, backups, logs—sits in object storage. Not in databases. Not in file systems. In giant key-value warehouses.

---

## Quick Recap (5 bullets)

- **Block storage:** Raw bytes, no file system. Used by databases and VMs. Fastest. EBS, Persistent Disk.
- **File storage:** Hierarchical paths, folders. NFS, EFS. Great for shared file systems.
- **Object storage:** Flat key-value. S3, GCS, Azure Blob. Cheapest, most scalable.
- **When to use:** Block = DBs, VMs. File = shared docs, home dirs. Object = images, videos, backups, logs.
- **Instagram, Netflix, Dropbox:** All rely heavily on object storage for user content.

---

## One-Liner to Remember

Block = raw room you organize. File = filing cabinet with paths. Object = warehouse with a ticket for every box.

---

## Next Video

Next up: Object storage in depth. How does S3 really work? What's inside the box? Stay tuned.
