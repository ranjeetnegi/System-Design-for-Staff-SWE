# When to Use Object Storage vs Database

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You have family photos. And a family tree. Would you store photos in a spreadsheet? Would you store "grandmother of John" as a JPEG?

Right tool for the right job. Object storage for blobs. Database for structure. Mix them wrong and things break fast.

---

## The Story

Maria has two kinds of family treasures. Photos from reunions, vacations, birthdays. Hundreds of gigabytes. And a family tree—names, relationships, who married whom, who is whose grandparent. She needs both.

If she stored every photo as a row in a spreadsheet, it would be absurd. Slow. Awkward. Spreadsheets aren't built for huge binary blobs.

If she stored the family tree as a single JPEG, she couldn't query it. "Who is my grandmother?"—she'd have to open the image and look. No search. No relationships.

So: photos go in a photo album—or in the cloud as objects. Large files, rarely queried by content, stored for years. The family tree goes in a structured place—a database, a graph, something you can query. "SELECT * FROM people WHERE relationship = 'grandmother'."

Object storage = large blobs. Database = structured, queryable data. Different problems. Different tools.

But here's where things go wrong: teams sometimes try to force everything into one system. "Let's put images in the database—simpler!" Or "Let's query object storage for metadata—cheaper!" Both fail at scale. Respect the boundaries. Use each tool for what it's built for.

---

## Another Way to See It

A library has books (the content) and a catalog (titles, authors, locations). The catalog says "Moby Dick is on Shelf 7, Row 3." You don't put the entire book IN the catalog. The catalog is small, searchable, relational. The book is big, stored once, retrieved by call number.

Object storage holds the books. Database holds the catalog. Same idea in software.

---

## Connecting to Software

**Object storage is for:** Images, videos, PDFs, backups, logs, static files. Large. Unstructured. Rarely queried by content. You store by key, retrieve by key. No JOINs. No complex queries.

**Database is for:** Users, orders, transactions, relationships. Structured. Frequently queried. Needs indexes, JOINs, consistency. You ask "all orders by user 123" or "total revenue last month." The database is built for that.

**The common pattern:** Store the FILE in object storage (S3). Store the METADATA in the database (PostgreSQL). Example: a post table. `{id, user_id, caption, image_url: "s3://bucket/posts/photo123.jpg"}`. The database holds the URL. The actual image lives in S3. Best of both worlds.

**Size matters:** Databases struggle with rows over a few hundred KB or 1MB. Object storage handles gigabyte-sized files easily. Put the blob in object storage. Put the pointer in the database.

The aha moment: you're not choosing one OR the other. You use BOTH. The database is your index. The object store is your warehouse. They work together. Every well-designed media app does this.

---

## Let's Walk Through the Diagram

```
┌──────────────────────────────────────────────────────────┐
│                     YOUR APPLICATION                       │
└──────────────────────────────────────────────────────────┘
         │                              │
         │ Query: "Get post 456"        │ Fetch image by URL
         ▼                              ▼
┌─────────────────────┐      ┌─────────────────────────────┐
│     DATABASE         │      │      OBJECT STORAGE (S3)     │
│  id: 456             │      │  Key: posts/photo_456.jpg   │
│  user_id: 123        │      │  Value: [image bytes]       │
│  caption: "Beach!"   │      │                             │
│  image_url: s3://... │──────>  Metadata, searchable        │  Blob, large
└─────────────────────┘      └─────────────────────────────┘
```

Database = fast queries, relationships, small rows. Object storage = large blobs, cheap, scalable.

---

## Real-World Examples (2-3)

**Example 1 — Social media post:** The image file is in S3. The post record (user_id, caption, likes, comments, image_url) is in a database. You query the database for the feed. You use the URL to load the image from S3.

**Example 2 — Video streaming:** Video files in object storage. Metadata (title, description, duration, thumbnail URL, view count) in a database. You never query "what's inside the video." You query "top 10 trending" from the database, then stream the file from object storage.

**Example 3 — E-commerce:** Product images in S3. Product table (name, price, description, image_url) in PostgreSQL. The catalog is queryable. The images are served from object storage.

The pattern is universal. Any app that handles user-generated content—photos, documents, videos—separates the blob from the metadata. The blob scales with object storage. The metadata scales with databases. Two systems. One design.

---

## Let's Think Together

Video streaming app. Where do you store: (a) the video file, (b) video title and description, (c) thumbnails?

Pause and think.

(a) Video file → object storage. Huge. Streamed. No querying. (b) Title, description → database. Searchable, filterable, relational. (c) Thumbnails → object storage. They're images. Store the URL in the database. Same pattern everywhere: blobs in S3, metadata in DB.

The pattern repeats: Spotify stores audio files in object storage. Playlist metadata in a database. Google Drive stores files in object storage. File metadata and sharing info in Spanner. Once you see it, you see it everywhere.

---

## What Could Go Wrong? (Mini Disaster Story)

A team stored user-uploaded images as BLOBs inside PostgreSQL. "Simpler—one system!" It worked at 1,000 users. At 1 million, the database was 500GB. Backups took 8 hours. Queries slowed. Adding an index? Days.

One developer ran a full table scan. The database locked. Site down for an hour. The panic: "Why is everything slow?" The root cause: wrong storage. They migrated to S3. Took months. Downtime. Risk. Right tool from day one saves you. Don't learn this the hard way.

---

## Surprising Truth / Fun Fact

YouTube stores videos in a custom object storage system. The actual video bytes—petabytes of them—live there. Metadata—titles, views, comments, recommendations—lives in databases. Separation of concerns at planet scale.

---

## Quick Recap (5 bullets)

- **Object storage:** Large blobs—images, videos, PDFs, logs. Store by key. No queries.
- **Database:** Structured data—users, orders, relationships. Queryable. Indexed.
- **Common pattern:** File in S3, metadata (including URL) in database.
- **Size:** Databases hate multi-MB rows. Object storage loves GB-sized files.
- **Wrong choice:** BLOBs in DB → database balloons, backups slow, queries die.

---

## One-Liner to Remember

Blobs in object storage. Metadata in the database. Don't mix them up. Blobs in S3. Pointers in the database. That's the design. Stick to it.

---

## Next Video

When a user "deletes" something, is it really gone? Soft delete vs hard delete—and why it matters. Next up.
