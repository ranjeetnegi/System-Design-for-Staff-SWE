# What Is Object Storage?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A giant warehouse. You bring a box. They give you a ticket with a code. Want it back? Show the ticket. They fetch it. You can't open the box and change one item—you replace the whole thing. No folders. No hierarchy. Millions of boxes. Millions of tickets.

That's object storage. And it powers most of the internet.

---

## The Story

Imagine a warehouse the size of a city. You walk in with a box. The attendant takes it, scans it, hands you a slip: `box-2024-07-abc123`. That's your key. Your only way to get it back.

No shelves with labels. No "Section 3, Aisle 7." The warehouse doesn't care about organization. They have a system. You give them a box. They store it. You give them a key. They return it.

You can't say "open my box and change the third item." You have to bring a NEW box and say "replace the old one." The box is immutable. Replace, don't edit. That's how object storage works. Each object is like a sealed box. You overwrite it entirely or leave it alone.

Scale that to billions of boxes. Trillions. Each with a unique key. No directories. No tree. Just key → object. That's Amazon S3. That's Google Cloud Storage. That's the backbone of modern storage.

The emotional beat? At first it feels weird. "Where's my stuff? Just... somewhere?" But then you realize: you don't need to know. You have the key. The system handles the rest. Scale without complexity.

---

## Another Way to See It

Think of a coat check at a massive event. You hand over your coat. They give you a number. Ten thousand people. Ten thousand numbers. No names. No "John's coat goes in the blue section." Just number 48291. When you leave, you show the number. They fetch your coat. Fast. Simple. The system doesn't need to know what's IN the coat. It just needs the number.

Object storage is a coat check for data. The key is your number. The object is your coat.

---

## Connecting to Software

An **object** has three parts: the data itself (the bytes), metadata (tags, content-type, custom key-values), and a unique key. Like a box with a label.

The **namespace is flat.** No real directories. A key like `photos/vacation/beach.jpg` LOOKS like a path, but it's just a string. The system doesn't have folders. It has keys. S3 "prefixes" are a convenience for listing—not actual hierarchy.

**Immutable-ish:** You typically can't edit bytes inside an object. You PUT a new version (if versioning is on) or overwrite. Some systems support multipart uploads for large files—upload in chunks, then assemble. But you're still replacing, not patching.

**HTTP API:** PUT /bucket/key (upload), GET /bucket/key (download), DELETE /bucket/key (remove). Simple. RESTful. Everything goes over HTTP.

**Durability:** S3 claims 99.999999999%—eleven nines. Your data is replicated across multiple facilities. Losing an object is astronomically rare.

**Cost:** Pennies per GB per month. Way cheaper than block or file storage. But access latency is higher. Not for real-time, low-latency workloads.

Why does this design win? Because at scale, hierarchy breaks. Millions of "folders" becomes a nightmare. A flat key space scales infinitely. Add a key. Fetch by key. No tree to traverse. No locks on parent directories. Just... keys.

---

## Let's Walk Through the Diagram

```
        YOU                          S3 / OBJECT STORAGE
         │                                    │
         │  PUT /bucket/user123/photo.jpg     │
         │  [image bytes]                     │
         │ ─────────────────────────────────>│
         │                                    │
         │  200 OK, key: user123/photo.jpg   │
         │ <─────────────────────────────────│
         │                                    │
         │  GET /bucket/user123/photo.jpg     │
         │ ─────────────────────────────────>│
         │                                    │
         │  [image bytes]                     │
         │ <─────────────────────────────────│
         │                                    │
```

You upload. You get a key. You download with the key. No "open and edit byte 5." Replace the whole object or leave it.

---

## Real-World Examples (2-3)

**Example 1 — AWS S3:** The original. Petabytes for Netflix, Airbnb, thousands of companies. Images, backups, logs, data lakes. Everything.

**Example 2 — Google Cloud Storage:** Same idea. Used by YouTube, Gmail attachments (sometimes), BigQuery data. S3-compatible API in many ways.

**Example 3 — MinIO:** Self-hosted object storage. S3-compatible API. Run it in your own datacenter or Kubernetes. Same mental model, your infrastructure.

---

## Let's Think Together

You store user profile photos. Each user uploads a new photo. How do you generate the key? What about old photos?

Pause and think.

Common approach: `users/{user_id}/profile/avatar.jpg` or `users/{user_id}/profile/avatar_{timestamp}.jpg`. Include timestamp if you want to support multiple versions or avoid cache issues. Old photos? Either overwrite (same key) or keep both with versioning. Depends on whether you need history. Key design matters—too generic and you get collisions; too complex and listing becomes hard.

Think about collision resistance. If two users upload at the same millisecond, could you get the same key? Use UUIDs or include user_id. Never guess. Design for scale from day one.

---

## What Could Go Wrong? (Mini Disaster Story)

A company stored private documents in S3. They needed fast access, so they made the bucket public. "We'll fix permissions later." Weeks passed. A security researcher ran a simple script. Found thousands of private files. Employee data. Financial records. Customer PII. One misconfigured bucket. One of the top causes of data breaches.

The aftermath: fines. Lawsuits. Reputational damage. Object storage is powerful. Default to private. Lock it down. Always. Use IAM policies. Use presigned URLs for temporary access. Never expose a bucket to the world.

---

## Surprising Truth / Fun Fact

Dropbox started by storing files in S3. When they hit massive scale, the costs hurt. So they built their own object storage system—Magic Pocket—to save money. Billions of files. Custom infrastructure. All inspired by the same idea: key → object, at ridiculous scale.

---

## Quick Recap (5 bullets)

- **Object = data + metadata + unique key.** Like a box with a label.
- **Flat namespace.** No real folders. Keys can look like paths but are just strings.
- **Immutable-ish.** Replace the whole object; don't edit bytes in place.
- **HTTP API.** PUT, GET, DELETE. Simple. RESTful.
- **Durability & cost.** Eleven nines durability. Pennies per GB. Higher latency than block/file.

---

## One-Liner to Remember

Object storage: you give them a box, they give you a ticket. Show the ticket, get the box back. No folders. Just keys.

---

## Next Video

When do you use object storage versus a database? Photos in S3, user data in PostgreSQL—why the split? Next video: Object storage vs database.
