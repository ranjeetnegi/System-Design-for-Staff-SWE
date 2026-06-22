# Chapter 61g: File Sync Service — Dropbox / Google Drive

> Dropbox's core promise is: edit a file on your laptop, and it appears on
> your phone in seconds. The hard part isn't storage — it's detecting what
> changed, sending only the difference, and handling conflicts when two
> devices edit the same file offline.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — File Sync Service                          |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (sync only? sharing? real-time edit?) |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                            |
|                                                                  |
|  The clarifying question that changes everything:                |
|  "Real-time collaborative editing (like Google Docs) or file-   |
|   level sync (like Dropbox)?" Real-time = CRDTs/OT, completely  |
|   different architecture. File-level sync = this chapter.       |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Chunking: 4MB chunks, SHA-256 per chunk                      |
|  - Delta sync: upload only changed chunks                       |
|  - Dedup: content-addressed chunk store (same hash = one copy)  |
|  - Conflict: keep-both (Dropbox approach) vs last-write-wins    |
|  - Notification: WebSocket push to connected devices             |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Resumable uploads: why UDP-like chunk protocol beats HTTP    |
|  - Cross-region bandwidth: peer-to-peer chunk transfer          |
|  - Metadata DB sharding by user_id (hot user problem)          |
|  - Bandwidth dedup: block-level dedup across all users (SDFS)  |
|  - Client sync loop state machine (6 states, race conditions)   |
+------------------------------------------------------------------+
```

---

## Why This Chapter Matters

File sync is asked at Dropbox, Google (Drive/Workspace), Box, Notion, Apple (iCloud), and Microsoft (OneDrive). It tests your ability to reason about client-server protocol design, which is rarer than pure backend design — most system design questions are server-to-server. The chunking insight (split file, hash chunks, upload only what changed) is the single most important concept. Interviewers know whether you've thought about this problem or are making it up as you go based on how quickly you explain chunking.

This is explicitly NOT the same as Ch52 (Object Storage). Ch52 covers the storage API — S3-like PUT/GET for arbitrary objects. This chapter covers the sync protocol: how clients detect changes, negotiate what to upload, and stay consistent across multiple devices and offline edits. An interviewer asking "design Dropbox" wants the sync protocol, not an S3 clone.

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify first

Before drawing: "Is this file-level sync (Dropbox model) or real-time collaborative editing (Google Docs model)? Those are completely different problems." If the interviewer says sync, continue here. If they say real-time editing, switch to CRDTs and operational transforms (different chapter).

Secondary clarifications:
1. "Does sharing with other users need to be in scope?" (adds permission model complexity)
2. "Do we need file version history, or just the latest version?"
3. "Mobile clients only, or desktop too?" (desktop has native file system watchers; mobile is event-driven)
4. "Target sync latency — 5 seconds? 30 seconds? 5 minutes?" (changes notification architecture)

For this chapter: file-level sync (not real-time editing), sharing supported, version history required, desktop + mobile, target sync latency 30 seconds.

### Who uses a file sync service?

**End users:**
- Knowledge worker saves a document on laptop → sees it on iPad on the commute home
- Designer uploads a Figma export → shares a folder with a client who can download it
- Developer pushes a configuration file → syncs to all team members who have the folder shared
- Student edits lecture notes on laptop (offline on a plane) → syncs when landing

**Devices per user:**
- Average: 2.5 devices (laptop + phone + tablet)
- Power users: 5-6 devices (work laptop, personal laptop, phone, iPad, work desktop)

### Core use cases

**P0 — Must have:**
- UC1: Upload a file → available on all user's devices within 30 seconds
- UC2: Download the latest version of a file on a new device
- UC3: Detect a local file change and sync delta to server
- UC4: Pull updates from server when a shared file changes

**P1 — Important:**
- UC5: Share a folder with another user (read or write access)
- UC6: View version history for a file (last 30 days)
- UC7: Restore a previous version of a file
- UC8: Conflict resolution when two devices edit the same file offline

**Out of scope:**
- Real-time collaborative editing within a document (Google Docs, Notion — different architecture)
- Full-text search within file contents
- Video streaming or media transcoding

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Core protocol operations

- **F1:** `upload_file(path, content) -> file_id, version` — upload new or updated file
- **F2:** `download_file(file_id, version) -> content` — download a specific version
- **F3:** `check_chunks(chunk_hashes[]) -> missing_hashes[]` — ask server which chunks it needs
- **F4:** `upload_chunk(hash, bytes)` — upload one chunk
- **F5:** `get_metadata(path) -> {file_id, version, modified_at, chunk_list}` — fetch file metadata
- **F6:** `list_changes(since_version) -> [{file_id, path, version, modified_at}, ...]` — poll for changes
- **F7:** `create_conflict_copy(file_id, device_id) -> new_file_id` — server-side conflict resolution

### Storage operations (for the user-facing product)

- **F8:** `share_folder(folder_id, user_email, permission)` — share with another user
- **F9:** `list_versions(file_id) -> [version, ...]` — get version history
- **F10:** `restore_version(file_id, version)` — make an older version the current version

### What makes this different from a simple file server

```
The problem with naive approach (upload full file):
  User has a 2GB video file. They fix a typo in embedded metadata. (1 change)
  Naive: re-upload 2GB. Takes 20 minutes on typical home internet (100 Mbps upload).
  Actual change: ~1KB of metadata.

  Even for a 10MB document, changing one paragraph:
  Naive: re-upload 10MB on every save. Dropbox auto-saves every 30s.
  10MB * 2 saves/min * 60 min * 8 hours = 9.6 GB uploaded per day per user.
  At 50M DAU: 480 petabytes/day ingested. Impossible.

The insight: chunking + delta sync
  Split file into 4MB fixed-size chunks.
  Compute SHA-256 hash per chunk.
  On every save: re-chunk, compute hashes, compare with last-known chunk list.
  Upload only the chunks whose hash changed.
  For a 10MB file (2-3 chunks), changing one paragraph: 1-2 chunks changed.
  Upload: 4-8MB instead of 10MB per change. Still good, but...

  Actual Dropbox uses variable-length chunking (content-defined chunking / Rabin fingerprinting):
    Chunks are defined by content patterns, not fixed size.
    Inserting a paragraph at the beginning: fixed chunking re-chunks everything after the insert.
    Variable chunking: only the affected "region" re-chunks. Rest of file unchanged.
  
  For L5 interview: fixed 4MB chunks is sufficient and correct.
  For L6: mention Rabin fingerprinting (variable-length chunks, better delta for insertions).
```

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### Traffic numbers

```
Total users:      500 million registered
DAU:               50 million active per day
Files stored:      10 billion total
File updates/day:   1 billion (20 per DAU)

Upload rate:
  1B updates/day / 86400s = 11,574 file updates/sec
  Delta sync: avg 20% of file changed per update -> avg 2 chunks uploaded per update
  11,574 updates/sec * 2 chunks * 4MB = 92.6 GB/sec bandwidth ingest
  This is the PEAK estimate. Average (off-peak): 1/3 of this = ~30 GB/sec.
  At $0.02/GB egress: 92.6 GB/sec * 86400s = 8 petabytes/day * $0.02 = $160K/day just in bandwidth

  In reality: deduplication (identical chunks across users) reduces this.
  Dropbox claims ~70% dedup ratio across their storage.
  Effective ingest: 30% of 8 PB = 2.4 PB unique data per day.

Download rate (read):
  Read/write ratio for file sync: ~1:1 (each upload triggers downloads on other devices)
  Each update: notifies 2.5 other devices on average -> 2.5x download amplification
  But devices often sync in batches, not immediately -> peak is smoothed

Storage:
  10B files, avg file size 500KB = 5 PB stored
  With version history (30 days, avg 5 versions/file): 5 * 5 PB = 25 PB
  With 70% chunk dedup: 25 * 30% = 7.5 PB actual storage needed
  At $0.02/GB: 7.5 PB * $20/TB = $150K/month storage cost
```

### Metadata math

```
Metadata per file:
  file_id (UUID):          16 bytes
  user_id:                  8 bytes
  path (avg 50 chars):     50 bytes
  version (int):            8 bytes
  modified_at (timestamp):  8 bytes
  chunk_hashes (10B/hash, avg 10 chunks/file): 320 bytes
  total per file:          ~410 bytes

10B files * 410 bytes = 4.1 TB of metadata
With 5 versions per file: 4.1 * 5 = 20.5 TB of metadata

A single Postgres instance holds up to ~10 TB comfortably.
At 20.5 TB: need metadata DB sharding (shard by user_id).
8 shards * ~2.5 TB each = manageable.
```

---

## Phase 4: Non-Functional Requirements (Minutes 14-19)

### Latency

- Sync latency: < 30 seconds from edit to appearance on other devices
- Upload API response: < 2 seconds for chunk receipt acknowledgment
- Metadata query: < 100ms (served from cache or indexed DB)

### Consistency

- **Eventual consistency:** A file uploaded on device A may take up to 30 seconds to appear on device B. This is by design — 30 seconds is the SLA, not a bug.
- **Strong consistency for metadata writes:** When a file is uploaded, the server must atomically update the version. Two devices uploading simultaneously must resolve to a single winning version + conflict copy. No lost writes.
- **Read-your-own-writes:** After uploading a file, the uploading client immediately sees the new version. Other clients see it within the sync window.

### Durability

- Chunks stored with 11 nines durability (S3-class). Multi-region replication.
- Metadata DB: synchronous replication to at least 2 replicas. No metadata lost on single node failure.
- Version history: retained for 30 days minimum. After 30 days: snapshots (one version per week).

### Availability

- 99.9% availability for sync. A 44-minute/month outage is acceptable.
- During outage: clients queue local changes and sync when service recovers. No data loss.

---

## Phase 5: Assumptions and Constraints

- A1: Maximum file size: 10 GB (chunked across 2,500 * 4MB chunks).
- A2: Chunk size: 4MB fixed. Simplifies implementation. Variable-length chunking would reduce bandwidth further (mention as extension).
- A3: A file's identity is its path within a user's drive. Moving a file = delete + create (or a special MOVE operation to avoid re-uploading).
- A4: Conflict resolution strategy: keep-both (Dropbox model). No automatic merge within files.
- A5: Clients are trusted (no adversarial upload). Chunk hash is used for dedup, not integrity verification (separate checksum for integrity).
- A6: Shared folders: all members see the same file state. Sharing is at the folder level, not per-file.

---

## Architecture Design — HLD

### Opening analogy

Imagine you have a document on your desk. You make a few edits. Before sending the updated document to your colleague, you compare it page-by-page to the previous version. You only photocopy and send the pages that changed — not the entire document. That is chunking and delta sync.

The post office (the notification service) then tells your colleague "new pages arrived." They go to the mailroom (chunk store), pick up only the new pages, and assemble the updated document.

### Full HLD diagram

```
[Laptop / Desktop Client]         [Mobile Client]
  File Watcher                      Event Trigger
       |                                 |
  Chunk Splitter                    Chunk Splitter
  SHA-256 per chunk                 SHA-256 per chunk
       |                                 |
       +-----------+     +---------------+
                   |     |
                   v     v
              +-----------+
              |  API      |
              |  GATEWAY  |
              |  (auth,   |
              |  rate lim)|
              +-----------+
              /           \
             /             \
     +----------+     +-----------+
     | UPLOAD   |     | METADATA  |
     | SERVICE  |     | SERVICE   |
     |          |     |           |
     | 1.check  |     | file tree |
     |   chunks |     | versions  |
     | 2.receive|     | sharing   |
     |   chunks |     | perms     |
     | 3.commit |     +-----------+
     |   meta   |          |
     +----------+     +----+------+
          |           | Postgres  |
          |           | (metadata)|
          v           +-----------+
     +-----------+
     | CHUNK     |
     | STORE     |
     | (S3-like) |
     | key=SHA256|
     +-----------+
          |
          v
     +-----------+
     | MESSAGE   |
     | QUEUE     |
     | (Kafka)   |
     +-----------+
          |
          v
     +--------------------+
     | NOTIFICATION SVC   |
     | WebSocket + long   |
     | poll + APNs/FCM    |
     +--------------------+
          |
          +--------> All connected devices of the user (and shared-folder members)
```

### Component responsibilities

```
+-------------------+----------------------------------+-----------+-----------------+
| Component         | Responsibility                   | Stateful? | Scale target    |
+-------------------+----------------------------------+-----------+-----------------+
| Upload Service    | Receives chunks, stores to S3,   | NO        | 11K uploads/sec |
|                   | triggers metadata update         |           | 10 instances    |
+-------------------+----------------------------------+-----------+-----------------+
| Metadata Service  | CRUD on file tree, versions,     | NO        | 50K reads/sec   |
|                   | sharing permissions              |           | 5 instances     |
+-------------------+----------------------------------+-----------+-----------------+
| Chunk Store       | Content-addressed object storage | YES       | 92 GB/sec ingest|
|                   | Key = SHA-256, immutable blobs   |           | S3 + CDN        |
+-------------------+----------------------------------+-----------+-----------------+
| Metadata DB       | PostgreSQL, sharded by user_id   | YES       | 20.5 TB total   |
|                   | File tree, chunk lists, versions |           | 8 shards        |
+-------------------+----------------------------------+-----------+-----------------+
| Notification Svc  | WebSocket for desktop; APNs/FCM  | YES       | 50M devices     |
|                   | for mobile. Pushes sync events   |           | connected       |
+-------------------+----------------------------------+-----------+-----------------+
| Kafka             | Decouples upload from notify.    | YES       | 11K events/sec  |
|                   | Topic: file-sync-events          |           | RF=3            |
+-------------------+----------------------------------+-----------+-----------------+
| Redis             | Online device registry:          | YES       | 50M entries     |
|                   | {user_id -> [device_ids]}        |           | 100 MB          |
|                   | Also: upload session state       |           |                 |
+-------------------+----------------------------------+-----------+-----------------+
```

---

## Component 1: The Sync Protocol — Upload Path

**This is the core mechanism. Know every step.**

### The chunking process (client-side)

```
File: "quarterly_report.docx" (10 MB)

Step 1: Split into 4MB chunks
  Chunk 0: bytes 0        to 4,194,303     (4 MB)
  Chunk 1: bytes 4,194,304 to 8,388,607    (4 MB)
  Chunk 2: bytes 8,388,608 to 9,999,999    (1.6 MB, last chunk — smaller)
  Total: 3 chunks

Step 2: Compute SHA-256 hash per chunk
  chunk_0_hash = SHA256(bytes 0..4MB)   = "a3f2c1..."
  chunk_1_hash = SHA256(bytes 4..8MB)   = "b7e4d2..."
  chunk_2_hash = SHA256(bytes 8..10MB)  = "c9f3a1..."

Step 3: Check local cache (previous sync state)
  Client stores: {file_path -> [hash_0, hash_1, hash_2]} from last sync
  If previous state matches current hashes: no change. Skip.

Step 4: Compute delta (which chunks changed)
  Previous chunk list: [hash_0_old, hash_1, hash_2]
  Current chunk list:  [hash_0_new, hash_1, hash_2]
  Changed: chunk 0 (hash_0_old != hash_0_new)
  Unchanged: chunks 1, 2

Step 5: Ask server which chunks it needs (check_chunks API)
  POST /chunks/check
  {chunk_hashes: ["hash_0_new"]}
  
  Server response:
  {missing: ["hash_0_new"]}  -- server does not have this chunk
  or
  {missing: []}              -- server already has it (another user uploaded same content)

Step 6: Upload only missing chunks
  PUT /chunks/hash_0_new  (body: 4MB bytes)
  Server stores: chunk_store["hash_0_new"] = bytes

Step 7: Commit metadata update
  POST /files/metadata
  {
    file_id:     "file_123",
    path:        "/quarterly_report.docx",
    version:     5,
    chunk_list:  ["hash_0_new", "hash_1", "hash_2"],
    modified_at: "2024-12-24T10:30:00Z",
    device_id:   "device_laptop_abc"
  }
  Server: updates metadata DB, publishes sync event to Kafka
```

### Content-addressed storage and deduplication

```
Key insight: chunks are addressed by their SHA-256 hash, not by file or user.
  Two users upload identical files -> same chunk hashes -> one copy stored.
  Same document template shared among 10,000 users -> 10,000 metadata records
  but only ONE copy of each chunk in storage.

Deduplication rate in practice:
  Business documents (templates, policies, forms): very high dedup (~80%)
  Personal photos: low dedup (each photo is unique)
  Code repositories: moderate dedup (boilerplate files are shared)
  Overall: Dropbox reported ~70% dedup across their storage.

Storage savings calculation:
  Without dedup: 10B files * 500KB avg = 5 PB
  With 70% dedup: 5 PB * 30% = 1.5 PB unique storage

Security consideration:
  Content-addressed dedup means: if two users have the same file,
  user A's upload is "found" as user B's existing chunk.
  Privacy concern: don't expose the fact that chunk X exists to unauthorized users.
  The check_chunks API should only return "already have it" if the REQUESTING user
  has previously uploaded that chunk themselves. Cross-user dedup happens silently.
  (The chunk is stored once, but each user's metadata record is independent.)
```

### The download path

```
On receiving a sync notification (or on-demand download):

Step 1: Fetch metadata
  GET /files/metadata?file_id=file_123&version=latest
  Response: {chunk_list: ["hash_0_new", "hash_1", "hash_2"], total_size: 10MB}

Step 2: Check local cache (which chunks already downloaded?)
  Client has chunk_1 and chunk_2 locally (unchanged from previous version).
  Only chunk_0_new is missing locally.

Step 3: Download only missing chunks
  GET /chunks/hash_0_new
  Response: 4MB bytes

  CDN serves chunk downloads (chunks are immutable, cacheable forever).
  Cache-Control: max-age=31536000 (1 year) — content never changes for a given hash.

Step 4: Reassemble file locally
  Concatenate: chunk_0_new + chunk_1 + chunk_2 = 10MB file
  Write to local path: "/quarterly_report.docx"
  Update local sync state: {"/quarterly_report.docx" -> ["hash_0_new", "hash_1", "hash_2"]}
```

---

## Component 2: File System Watching (Client)

**Interviewers sometimes probe the client side. Know which OS API does what.**

### OS-level file system events

```
macOS:      FSEvents API
  kqueue + FSEventStream: low-overhead event subscription
  Events: kFSEventStreamEventFlagItemCreated, ...Modified, ...Removed, ...Renamed
  Latency: sub-100ms for local changes

Linux:      inotify API
  inotify_create1() + inotify_add_watch()
  Events: IN_MODIFY, IN_CREATE, IN_DELETE, IN_MOVED_FROM, IN_MOVED_TO
  Latency: sub-millisecond
  Limitation: recursive watching requires adding watches for each subdirectory

Windows:    ReadDirectoryChangesW API
  Watches a directory tree for changes
  Events: FILE_ACTION_ADDED, FILE_ACTION_MODIFIED, FILE_ACTION_REMOVED, FILE_ACTION_RENAMED_*

Mobile (iOS/Android):
  No persistent background process that watches the file system.
  Sync triggered by: explicit app open, background app refresh (iOS), WorkManager (Android).
  Typically: sync on app open + schedule background check every 15 minutes.
```

### Client-side debouncing

```
Problem: text editors save-as-you-type, triggering dozens of inotify events per second.
  Word auto-saves every 30 seconds. Each auto-save: 5-10 inotify events.
  Without debouncing: 5-10 sync cycles per auto-save, all redundant.

Fix: debounce with a 2-second quiet period.
  On inotify event: start a 2-second timer.
  If another event arrives before timer fires: reset the timer.
  When timer fires (2 seconds of no events): trigger one sync cycle.
  
  This collapses rapid edits into a single sync trigger.
  Trade-off: adds 2 seconds to sync latency (well within the 30s SLA).

Also: ignore hidden/temp files created by editors:
  .docx (Word temp files), .~lock.file (LibreOffice), .DS_Store (macOS metadata)
  Filter rules: exclude files matching *.tmp, ~$*, .* patterns.
```

### Client state machine

```
6 states per file in the client:

SYNCED: local file matches server version. No action needed.

MODIFIED_LOCAL: local file changed. Client needs to upload.
  Triggered by: inotify event.

UPLOADING: client is actively uploading chunks to server.
  If interrupted: resume from last chunk (resumable upload).

MODIFIED_REMOTE: server version is newer than local. Client needs to download.
  Triggered by: sync notification from server.

DOWNLOADING: client is actively downloading chunks from server.

CONFLICT: local version modified AND remote version modified since last sync.
  Resolution: keep-both (create conflict copy).

Transitions:
  SYNCED -> MODIFIED_LOCAL: inotify event
  MODIFIED_LOCAL -> UPLOADING: sync timer fires
  UPLOADING -> SYNCED: upload complete + metadata committed
  UPLOADING -> MODIFIED_LOCAL: upload interrupted (retry)

  SYNCED -> MODIFIED_REMOTE: sync notification received
  MODIFIED_REMOTE -> DOWNLOADING: client starts download
  DOWNLOADING -> SYNCED: download complete

  MODIFIED_LOCAL + sync notification -> CONFLICT: both modified
  CONFLICT -> SYNCED: conflict copy created, original downloaded
```

---

## Component 3: Conflict Resolution

**Interviewers ALWAYS ask about offline edits. Know Dropbox's approach vs alternatives.**

### The conflict scenario

```
Timeline:
  T=0:   User edits "report.docx" on laptop. Laptop goes offline.
  T=1:   User edits the same "report.docx" on phone (also offline).
  T=2:   Laptop comes online. Uploads changes. Server: version 5 committed.
  T=3:   Phone comes online. Tries to upload changes.
         Server has version 5. Phone's base version was version 4 (pre-edit).
         Phone's upload: based on version 4 -> CONFLICT detected.

Conflict detection:
  When phone commits metadata, it includes: base_version = 4
  Server checks: is version 4 still the latest for this file?
  Server: latest version = 5 (laptop's upload). Version 4 is not latest.
  Server: CONFLICT. Returns HTTP 409 Conflict.
```

### Strategy 1: Keep-Both (Dropbox model) — recommended

```
On conflict:
  1. Server keeps the laptop's version (version 5) as the "canonical" version.
  2. Server creates a conflict copy for the phone's version:
     filename: "report (Jane's conflicted copy 2024-12-24).docx"
     This becomes a new file with its own metadata and chunk list.
  3. Both devices sync:
     - Laptop sees: "report.docx" (its own version, no change)
     - Phone sees:  "report.docx" (laptop's version, downloaded)
                    "report (Jane's conflicted copy 2024-12-24).docx" (phone's version)
  4. User manually merges the two files. Dropbox shows a notification.

Advantages:
  - No data loss (both versions preserved)
  - Simple to implement (no merge logic in the server)
  - User is in control of merge decision

Disadvantages:
  - User must manually resolve. For power users with frequent conflicts: frustrating.
  - Proliferates "conflicted copy" files if not cleaned up.

When is this acceptable?
  File-level sync (Dropbox, Google Drive basic): YES. Users understand files.
  Real-time collaborative editing (Google Docs): NO. Must merge automatically.
```

### Strategy 2: Last-Write-Wins (timestamp)

```
On conflict: whichever upload has the later modified_at timestamp wins.
  Phone's edit: modified_at = T=1 (10:01 AM)
  Laptop's edit: modified_at = T=0 (10:00 AM)
  Phone wins (later timestamp). Laptop's changes are silently discarded.

Disadvantages:
  - Silent data loss (laptop's changes gone, no notification)
  - Clock skew: device clocks can differ by minutes. Laptop's clock might be wrong.
  - Unfair: a device with a fast clock always "wins" conflicts.

Use case: Only acceptable for files that are log files or purely additive records,
where the latest version is always better than the earlier one.
Avoid for any file where both edits might be meaningful.
```

### Strategy 3: Operational Transform / CRDT (out of scope)

```
Used for: real-time collaborative editing (Google Docs, Notion, Figma).
Not applicable to file-level sync (we do not have insight into the file's internal structure).

Mention briefly: "If the interviewer asks about real-time editing, OT and CRDTs
are the right tools. For file-level sync, we use keep-both or last-write-wins."
```

### Conflict detection via version vectors

```
Version vector: each device maintains its own counter for updates.
  file "report.docx" version vector:
    {laptop: 3, phone: 0}  -- laptop has made 3 edits, phone has seen all of them

  After laptop's offline edit: {laptop: 4, phone: 0} (phone's counter stale)
  After phone's offline edit:  {laptop: 3, phone: 1} (phone made edit from base)

  When both come online:
    Server has: {laptop: 4, phone: 0}
    Phone uploads: {laptop: 3, phone: 1}

    Conflict condition: neither dominates the other.
      Server's {laptop:4, phone:0} is NOT >= Phone's {laptop:3, phone:1}
      (laptop counter: server 4 >= phone 3. phone counter: server 0 < phone 1)
      -> CONCURRENT edits -> CONFLICT

    If phone's upload is: {laptop:4, phone:1} (phone had seen laptop's edit first)
      -> phone's version DESCENDS FROM server's version -> no conflict, just an update.

Version vectors are more accurate than timestamps for conflict detection.
Timestamps can have clock skew; version vectors are logical.
Dropbox reportedly uses vector clocks for device sync.
```

---

## Component 4: Notification System — Pushing Sync to Devices

**Interviewers ask: "How does device B know device A uploaded a file?"**

### Connection types

```
Desktop clients (laptop, desktop):
  - Persistent WebSocket connection to Notification Service
  - Connection maintained as long as Dropbox app is running
  - Reconnect with exponential backoff on disconnect

Mobile clients (phone, tablet):
  - NOT a persistent WebSocket (battery/data cost too high)
  - Instead: APNs (Apple Push Notification Service) for iOS
              FCM (Firebase Cloud Messaging) for Android
  - On receiving push: app wakes up in background, pulls sync update

Web clients (browser):
  - Server-Sent Events (SSE) or long poll
  - SSE: browser holds open HTTP connection, server pushes events one-way
  - Long poll: browser sends request, server holds it open for 30s, responds when event arrives
```

### WebSocket notification flow

```
Step 1: User opens Dropbox on laptop.
  Client -> WS server: CONNECT
  WS server: register in Redis: SET device:{device_id} ws_server_node_3
  Also: SADD user:{user_id}:devices device_id
  Now server knows this user's device is connected to WS node 3.

Step 2: Another device uploads a file change.
  Upload Service -> Kafka: publish {user_id, file_id, version, modified_at}

Step 3: Notification Service consumes from Kafka.
  For the uploading user: find all connected devices.
  Redis: SMEMBERS user:{user_id}:devices -> [device_laptop_abc, device_phone_xyz]
  For device_laptop_abc: GET device:{device_laptop_abc} -> ws_server_node_3
  For device_phone_xyz: GET device:{device_phone_xyz} -> nil (not connected via WS)
  
  -> Push WebSocket message to ws_server_node_3 for device_laptop_abc
  -> Send APNs/FCM push to device_phone_xyz

Step 4: Laptop client receives WebSocket event.
  {event: "file_updated", file_id: "file_123", version: 5, path: "/report.docx"}
  Client: "I have version 4 locally. Server has version 5. Start download."
  Transition: SYNCED -> MODIFIED_REMOTE -> DOWNLOADING -> SYNCED

Step 5: Phone receives FCM push.
  Phone wakes background app process.
  App: GET /files/changes?since_version=4&user_id=...
  Server returns list of changed files.
  App downloads the changed chunks and syncs.
```

### Handling shared folders

```
When user A updates a file in a folder shared with users B, C, D:
  Upload Service publishes: {file_id, version, changed_by: user_A}
  
  Notification Service: look up all members of the folder.
  SELECT user_id FROM folder_members WHERE folder_id = file.folder_id
    -> [user_A, user_B, user_C, user_D]
  
  Exclude the uploader (user_A already has the file locally):
    -> [user_B, user_C, user_D]
  
  For each user: send sync notification to all their connected devices.
  
  Fan-out: 1 file change -> 3 users * 2.5 devices each = 7.5 notifications per change.
  At 11K changes/sec: 82.5K notification events/sec.
  Redis and WebSocket server must handle this fan-out rate.

Large shared folders (1,000 members):
  1 file change -> 999 users * 2.5 devices = 2,497 notifications
  At 11K changes/sec: 27.5M notifications/sec
  This is expensive. For very large shared folders, consider:
    - Notification batching (group changes per user, send one batch per 5 seconds)
    - Pull-based sync for large groups (clients poll instead of server pushing)
    - Cursor-based: each client polls GET /changes?cursor=X to get changes since last sync
```

---

## Component 5: Resumable Uploads

**L6 depth: the "what happens if the upload is interrupted?"**

### Why large file uploads need resumability

```
Uploading a 10 GB file at 100 Mbps upload speed:
  10 GB / (100 Mbps / 8) = 10 GB / 12.5 MB/s = 800 seconds = ~13 minutes

Network interruption probability in 13 minutes on typical home ISP: ~10-20%
Without resumability: interrupted upload = start over from the beginning.
Users would give up. 10 GB file never syncs.

With chunking (4MB chunks): upload 2,500 chunks.
  If network drops at chunk 1,500: resume from chunk 1,501.
  Already uploaded: 1,500 * 4MB = 6 GB. Remaining: 1,000 * 4MB = 4 GB.
  No wasted bandwidth (each chunk either stored or not).
  Exactly-once: chunk store is content-addressed. Re-uploading chunk 1,500 with same hash
  is idempotent (server deduplicates). No corruption.
```

### Resumable upload protocol

```
Step 1: Initiate upload session
  POST /uploads/initiate
  {file_id, chunk_count: 2500, chunk_hashes: [...2500 hashes...]}
  Server responds: {session_id: "upload_sess_abc", missing_chunks: [0, 1, 5, 7, ...]}
  (missing_chunks = chunks not yet in chunk store)
  
  Server records: upload_sessions[session_id] = {
    file_id, expected_chunks: 2500,
    received_chunks: {}  (empty set initially)
  }

Step 2: Upload chunks (can be parallel, out of order)
  PUT /chunks/{chunk_index}
  Header: X-Upload-Session: upload_sess_abc
  Body: 4MB chunk bytes
  
  Server: store chunk to S3, mark received_chunks.add(chunk_index)
  Server: SET upload_session:{session_id}:chunk:{chunk_index} 1 EX 86400

Step 3: On network interruption
  Client tracks which chunks were confirmed received (got HTTP 200).
  On reconnect: POST /uploads/status?session_id=upload_sess_abc
  Server responds: {received_chunks: [0, 1, 5, 7, ...], missing_chunks: [2, 3, 4, 6, ...]}
  Client: resume uploading only the missing chunks.

Step 4: Commit (all chunks uploaded)
  POST /uploads/commit?session_id=upload_sess_abc
  Server: verify all 2500 chunks received.
  Update metadata: file version, chunk list, modified_at.
  Publish sync event to Kafka.
  Return: {file_id, version: 3, status: "committed"}

Session TTL:
  Upload sessions expire after 24 hours of inactivity.
  If user doesn't complete the upload within 24 hours: session deleted.
  Uploaded chunks may remain in chunk store (as orphaned chunks, eventually GC'd).
  Client must re-initiate the upload.
```

---

## API Design

### Check Chunks (Delta Sync)
```
POST /v1/files/chunks/check
Request:  { chunk_hashes: [sha256_hex] }  -- batch, max 1000
Response: { missing: [sha256_hex] }       -- only hashes NOT on server
Notes:    privacy-safe: only confirms existence if requesting user owns it
```

**Why this shape:** The client has already computed SHA-256 per chunk locally. It sends ALL chunk hashes for the changed file (not just the ones it thinks are new — the server is the source of truth). The server cross-references against the requesting user's own prior uploads. This is a read-only existence check — no data is transferred. The client then uploads only the chunks in the `missing` list.

**Max 1000 per batch:** A 4 GB file has 1,000 chunks. Larger files require multiple batches. This prevents accidental DoS from a client sending 10,000 hashes in a single request.

---

### Upload Chunk
```
PUT /v1/files/chunks/{sha256_hex}
Request body: raw bytes (4MB max)
Response: { chunk_id: sha256_hex, size: int }
Headers:  Content-Length required; 409 if chunk already exists (idempotent)
```

**Why PUT (not POST):** PUT is idempotent by HTTP convention. If the client retries a failed chunk upload, the server receives the same bytes twice. Same hash → same S3 key → no-op write. The 409 response (Conflict) on retry tells the client "already have this chunk" without wasting bandwidth re-storing it.

**Content-Length required:** Forces the client to know the chunk size before uploading. Prevents chunked transfer encoding, which complicates S3 streaming and makes quota enforcement harder (quota check happens before the upload, based on declared size).

---

### Create/Update File (Metadata Commit)
```
POST /v1/files
Request:  { path: string, chunk_hashes: [sha256_hex], parent_version: string }
Response: { file_id: string, version_id: string, conflict: bool }
Notes:    parent_version used for conflict detection (version vectors);
          conflict=true means keep-both resolution was applied
```

**Why parent_version:** The server needs to know what version the client was editing from. If device A commits version N+1 and device B also tries to commit a new version based on version N, the server detects concurrent edits (both had `parent_version = N`). This is the conflict detection gate. Without it, the server cannot distinguish a legitimate update from a stale overwrite.

**conflict=true response:** When a conflict is detected, the server does NOT reject device B's upload. It creates a conflict copy and commits it as a sibling file. The `conflict: true` flag tells device B's client to notify the user that a conflict copy was created and they need to manually merge. This way no data is lost.

---

### List Changes (Cursor-Based Pull)
```
GET /v1/files/changes?cursor=base64token&limit=500
Response: { changes: [{file_id, path, version_id, op: CREATED|MODIFIED|DELETED}],
            next_cursor: string, has_more: bool }
Notes:    cursor encodes (user_id, last_seq_id); client polls this as fallback
          when WebSocket push is unavailable
```

**Why cursor-based (not timestamp-based):** Timestamps have clock skew. If two writes happen at the same millisecond, a timestamp cursor misses one of them on the next poll. A sequence ID (`seq_id BIGSERIAL`) is strictly monotonic and server-assigned — no skew, no missed events. The cursor is opaque to the client (base64-encoded); the client never interprets it, it just sends it back on the next request.

**Fallback role:** Clients ALWAYS poll this endpoint on startup (to catch changes missed while offline). WebSocket push is a performance optimization that reduces the polling interval to near-zero for connected clients. If the WebSocket drops, the client falls back to polling every 30 seconds. The system is eventually consistent via polling alone even if the entire notification tier is down.

**limit=500:** Caps response size. If 5,000 files changed while the device was offline for a week, the client pages through the results: first 500, then cursor → next 500, etc. This prevents a single response that blows up client memory.

---

### Get Download URL
```
GET /v1/files/{file_id}/download?version=latest
Response: { url: string (pre-signed S3, 1h TTL), expires_at: timestamp }
```

**Why pre-signed S3 URL (not proxied download):** If the server proxied downloads, every file download would consume Upload Service bandwidth and CPU. At 50M DAU downloading files constantly, this is prohibitive. A pre-signed S3 URL lets the client download directly from S3 (or the CDN in front of it) without touching the application servers. The URL is signed with the server's AWS credentials and has a 1-hour TTL — expired URLs are rejected by S3, preventing stale URL reuse after a user's access is revoked.

**Serving entire file vs. chunks:** The download URL returns the assembled file, not individual chunk URLs. The CDN reassembles chunks or the S3 multipart object is pre-assembled at commit time. Clients do not need to know about chunks at download time — that is an internal storage detail.

---

## Component 6: Metadata DB Schema

### PostgreSQL schema

```
Table: users
+---------------+--------+------------------------+
| Column        | Type   | Notes                  |
+---------------+--------+------------------------+
| user_id       | UUID   | PK                     |
| email         | TEXT   | UNIQUE                 |
| storage_quota | BIGINT | bytes (e.g., 15GB)     |
| storage_used  | BIGINT | bytes                  |
+---------------+--------+------------------------+

Table: files
+------------------+----------+------------------------------------------+
| Column           | Type     | Notes                                    |
+------------------+----------+------------------------------------------+
| file_id          | UUID     | PK                                       |
| owner_user_id    | UUID     | FK users. Shard key.                     |
| folder_id        | UUID     | FK folders (NULL for root)               |
| filename         | TEXT     | Just the name, not full path             |
| is_deleted       | BOOLEAN  | Soft delete for 30-day recovery          |
| created_at       | TIMESTMP |                                          |
+------------------+----------+------------------------------------------+
Index: (owner_user_id, folder_id) -- list files in a folder
Sharding: by owner_user_id (8 shards)

Table: file_versions
+------------------+----------+------------------------------------------+
| Column           | Type     | Notes                                    |
+------------------+----------+------------------------------------------+
| file_id          | UUID     | FK files                                 |
| version          | INT      | Monotonically increasing per file        |
| chunk_hashes     | TEXT[]   | Ordered array of SHA-256 hashes          |
| total_size_bytes | BIGINT   |                                          |
| modified_at      | TIMESTMP |                                          |
| modified_by_dev  | UUID     | Which device uploaded this version       |
| base_version     | INT      | Which version this was based on          |
+------------------+----------+------------------------------------------+
PK: (file_id, version)
Index: (file_id, version DESC) -- get latest version
Retention: versions older than 30 days pruned by batch job

Table: chunks
+------------------+----------+------------------------------------------+
| Column           | Type     | Notes                                    |
+------------------+----------+------------------------------------------+
| chunk_hash       | CHAR(64) | SHA-256 hex string, PK                   |
| s3_key           | TEXT     | S3 object key (same as chunk_hash)       |
| size_bytes       | INT      |                                          |
| uploaded_at      | TIMESTMP |                                          |
| ref_count        | INT      | How many file_versions reference this    |
+------------------+----------+------------------------------------------+
Note: chunk GC happens when ref_count = 0 and chunk age > 7 days.

Table: folders
+------------------+----------+------------------------------------------+
| Column           | Type     | Notes                                    |
+------------------+----------+------------------------------------------+
| folder_id        | UUID     | PK                                       |
| owner_user_id    | UUID     | FK users                                 |
| parent_folder_id | UUID     | FK folders (NULL for root)               |
| name             | TEXT     |                                          |
+------------------+----------+------------------------------------------+

Table: folder_members (sharing)
+------------------+----------+------------------------------------------+
| Column           | Type     | Notes                                    |
+------------------+----------+------------------------------------------+
| folder_id        | UUID     | FK folders                               |
| user_id          | UUID     | FK users                                 |
| permission       | TEXT     | 'read', 'write', 'admin'                 |
| invited_at       | TIMESTMP |                                          |
+------------------+----------+------------------------------------------+
PK: (folder_id, user_id)
Index: (user_id) -- find all folders shared with this user
```

---

## DB Schema (Production DDL)

The following DDL is the production-quality version of the schema above. It adds version vectors for conflict detection, a `seq_id` cursor for the List Changes API, a normalized `version_chunks` join table (replaces the `TEXT[]` chunk_hashes array), and an atomic quota enforcement pattern.

```sql
CREATE TABLE files (
  file_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id     UUID         NOT NULL,
  path         TEXT         NOT NULL,
  is_deleted   BOOLEAN      NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (owner_id, path)
);
CREATE INDEX idx_files_owner ON files(owner_id);
```

**Why `UNIQUE (owner_id, path)`:** Path is how users refer to files. The same user cannot have two files at the same path. This unique constraint enforces that invariant at the DB layer rather than in application code. Without it, a race condition between two concurrent uploads to the same path could create duplicate rows.

```sql
CREATE TABLE file_versions (
  version_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id        UUID         NOT NULL REFERENCES files(file_id),
  version_vector JSONB        NOT NULL,  -- {device_id: seq_num} for conflict detection
  size_bytes     BIGINT       NOT NULL,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  seq_id         BIGSERIAL    NOT NULL   -- global change log cursor
);
CREATE INDEX idx_versions_file ON file_versions(file_id, created_at DESC);
CREATE INDEX idx_versions_seq  ON file_versions(owner_id, seq_id);  -- for cursor pull
```

**Why `version_vector JSONB`:** Version vectors are sparse — most files are only edited by 2-3 devices even if the user has 5 devices. A JSONB column stores `{"device_abc": 4, "device_xyz": 2}` compactly without a fixed schema. The index on `(owner_id, seq_id)` powers the List Changes cursor API: `WHERE owner_id = $uid AND seq_id > $last_seq LIMIT 500` is a pure index scan.

**Why `seq_id BIGSERIAL` on file_versions (not files):** The cursor needs to track at the version level, not the file level. A file can change 100 times; the client needs to catch up to the exact version it missed, not just know "this file changed." A BIGSERIAL provides a strictly monotonic server-assigned sequence with no clock skew.

```sql
CREATE TABLE chunks (
  sha256_hex   CHAR(64)     PRIMARY KEY,
  size_bytes   INT          NOT NULL,
  s3_key       TEXT         NOT NULL,
  ref_count    INT          NOT NULL DEFAULT 0,  -- GC: delete from S3 when 0 + 7d grace
  first_seen   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

**Why `ref_count` instead of a JOIN count:** Computing `SELECT COUNT(*) FROM version_chunks WHERE sha256_hex = ?` on every GC pass is expensive at billions of chunks. An explicit `ref_count` column is incremented/decremented at metadata commit time. The GC job then does `SELECT sha256_hex FROM chunks WHERE ref_count = 0 AND first_seen < NOW() - INTERVAL '7 days'` — a simple index scan. The 7-day grace window prevents a race where: chunk A is newly stored, not yet referenced in version_chunks, and GC runs in between.

```sql
CREATE TABLE version_chunks (
  version_id   UUID    NOT NULL REFERENCES file_versions(version_id),
  chunk_order  INT     NOT NULL,
  sha256_hex   CHAR(64) NOT NULL REFERENCES chunks(sha256_hex),
  PRIMARY KEY (version_id, chunk_order)
);
```

**Why a join table instead of `TEXT[] chunk_hashes`:** The Component 6 schema stores chunk hashes as a `TEXT[]` array column. This works but makes ref_count maintenance harder (you have to diff two arrays to find which chunks were added or removed on a version update). A normalized join table makes it easy: decrement ref_count for chunks in the old version_chunks rows, increment for chunks in the new rows. It also enables queries like "which files reference chunk X?" without a full table scan.

```sql
-- Quota enforcement (atomic check-and-update)
CREATE TABLE user_quotas (
  user_id        UUID    PRIMARY KEY,
  storage_used   BIGINT  NOT NULL DEFAULT 0,
  storage_limit  BIGINT  NOT NULL DEFAULT 17179869184  -- 16 GB default
);
-- Atomic quota check at file commit:
-- UPDATE user_quotas SET storage_used = storage_used + $delta
-- WHERE user_id = $uid AND storage_used + $delta <= storage_limit
-- rows_affected = 0 means quota exceeded (no partial update)
```

**Why atomic UPDATE instead of SELECT then UPDATE:** The SELECT-then-UPDATE pattern has a race condition: two concurrent uploads both read `storage_used = 14.9 GB`, both compute they fit under the 15 GB limit, both proceed. The atomic `UPDATE WHERE storage_used + delta <= limit` is evaluated in a single row lock by Postgres. Only one concurrent upload can win; the other gets `rows_affected = 0` and is rejected with HTTP 507 Insufficient Storage.

**Separation from `users` table:** Quota accounting is written on every chunk upload (high write frequency). The `users` table also holds email, auth tokens, and profile data (low write frequency, high read frequency). Splitting them onto separate tables reduces contention: quota writes do not block auth reads.

---

## Failure Scenarios

### Failure 1: Upload Service crashes mid-upload

```
Scenario: user uploads a 500MB file. At chunk 100 of 125, the Upload Service instance crashes.

Impact:
  - Chunks 0-99 are in the chunk store (S3). Safely stored.
  - Chunk 100 was in flight. May or may not have reached S3.
  - File metadata: not updated (crash before commit step).
  - Client: HTTP request timed out at chunk 100.

Recovery:
  Client: retry chunk 100 (same hash). PUT /chunks/{hash_100}.
  If chunk 100 was already stored (partial write succeeded): server returns 200 (idempotent).
  If not stored: server stores it now.
  Client continues uploading chunks 101-124.
  Client: POST /uploads/commit -> metadata updated.
  
  Session state persisted in Redis with TTL 24h. Upload session survives service crash.
  Client resumes by: POST /uploads/status -> get received_chunks -> continue.

Zero data loss: each chunk is atomic. Either stored or not. No partial chunks.
```

### Failure 2: Sync notification lost (device never syncs)

```
Scenario: Notification Service sends WebSocket event to device. Device is in a tunnel.
WebSocket connection drops. Event lost. Device never sees the "file updated" notification.

Impact: Device remains on stale version indefinitely.

Recovery (two layers):
  Layer 1: WebSocket reconnect. On reconnect, client sends:
    GET /files/changes?since_cursor=last_known_cursor
    Server returns all changes since the cursor, regardless of whether notifications were delivered.
    Client syncs the missed changes.
  
  Layer 2: Periodic poll (fallback). Even without a WS reconnect:
    Client polls GET /files/changes every 5 minutes (background refresh).
    Ensures eventual consistency within 5 minutes even if WS is broken.

Design principle: notifications are best-effort fast path. The cursor-based polling
is the guaranteed path. Never rely solely on push notifications for correctness.
```

### Failure 3: Metadata DB shard goes down

```
Scenario: metadata DB shard 3 (hosts users with user_id hash = 3) becomes unavailable.

Impact: 12.5% of users (1/8 of shards) cannot upload or access file metadata.
  Chunk uploads still work (chunk store is S3, independent of metadata DB).
  But: without metadata commit, uploads are orphaned.

Recovery:
  Metadata DB: synchronous replica. Promotion to primary in < 30 seconds.
  During 30s outage: uploads queue in the Upload Service (retry with backoff).
  After promotion: uploads commit metadata normally.
  
  RPO (Recovery Point Objective): 0 (synchronous replication, no data loss).
  RTO (Recovery Time to Objective): < 60 seconds (30s promotion + 30s client reconnect).
```

### Failure 4: Chunk store (S3) outage

```
Scenario: S3 region us-east-1 is down.

Impact: all chunk uploads and downloads fail. Complete service outage for affected region.

Mitigation (multi-region):
  Chunk store is S3 with cross-region replication to us-west-2.
  Upload Service: write to both regions (dual-write). Slow but durable.
  Or: write to primary, async replication to secondary. Accept 5-minute RPO.
  
  On us-east-1 outage: redirect traffic to us-west-2.
  Read availability: immediate (chunks replicated).
  Write availability: if dual-write: immediate. If async: up to 5 minutes of lost uploads.

Client behavior during S3 outage: uploads fail with 503. Client queues changes locally.
When service recovers: client drains the local queue. No data lost on client.
```

---

## Deep Concept Explanations

### Concept 1: Variable-Length Chunking (Rabin Fingerprinting)

Fixed-size chunking has a critical weakness: the "boundary shift problem."

```
Fixed 4MB chunks:
  File content: [AAAA][BBBB][CCCC][DDDD]
  (Each block represents 4MB)

  User inserts 1KB at the beginning: [1KB insert][AAAA][BBBB][CCCC][DDDD]

  New chunk boundaries:
    Chunk 0: [1KB insert][first 3MB of AAAA]  <- SHA-256 changes!
    Chunk 1: [last 1MB of AAAA][first 3MB of BBBB]  <- SHA-256 changes!
    Chunk 2: [last 1MB of BBBB][first 3MB of CCCC]  <- SHA-256 changes!
    Chunk 3: [last 1MB of CCCC][DDDD]  <- SHA-256 changes!
    Chunk 4: (nothing — total size increased)

  Result: ALL chunks have new hashes -> upload the entire file again.
  The 1KB insertion caused 100% upload amplification. Not efficient.

Rabin fingerprinting (content-defined chunking):
  Chunk boundaries are determined by the CONTENT, not position.
  The algorithm scans bytes and starts a new chunk when a specific pattern is found in the hash.
  
  Example: new chunk when (rolling_hash(64 bytes) & 0xFFF == 0x123)
  This pattern occurs statistically every 4096 bytes on average.
  
  After inserting 1KB at the beginning:
    Chunk 0: [1KB insert][some AAAA content] -- new chunk, ends at next fingerprint match
    Chunk 1: [remaining AAAA from after the fingerprint hit] -- likely same as before!
    Chunks 2, 3, 4: UNCHANGED (same content, same fingerprint hits, same boundaries)
  
  Result: only chunk 0 (or 0 and 1) changes. The rest are reused from cache.
  Upload: 4-8MB instead of entire file.

L5: fixed 4MB chunking is correct and sufficient for the interview.
L6: mention Rabin fingerprinting as the production-quality approach.
```

### Concept 2: Bandwidth Optimization at Global Scale

```
Problem: 50M DAU * avg 2 file updates/day * avg 2MB delta upload = 200 TB/day uploaded.
  At $0.09/GB egress (S3 standard): 200TB * $90/TB = $18,000/day in upload bandwidth.
  Plus download to other devices: 200TB * 2.5 devices * 1 chunk downloaded = 500TB * $90/TB = $45,000/day.
  Total: $63,000/day = $22.9M/year in bandwidth costs.

Optimization 1: CDN for downloads.
  Chunks are immutable (content-addressed). CDN caches chunks at edge.
  Cache hit rate: ~80% for popular content (shared business documents, templates).
  CDN cost: $0.01/GB vs S3 $0.09/GB -> 9x savings on cached content.
  Savings: 80% * 500TB * ($0.09 - $0.01) = $32,000/day saved.

Optimization 2: Client-to-client (peer-to-peer) chunk transfer.
  If device A and device B are on the same LAN (home network):
    Skip the server. Device B downloads chunk directly from device A.
    Bandwidth saved: chunk not uploaded to S3, not downloaded from S3.
    Dropbox "LAN sync": if Dropbox detects both devices on same network, uses UDP local broadcast.

Optimization 3: Compression before upload.
  For text files (documents, code): compress chunk before upload.
  LZ4: fast compression, typical 2:1 ratio for text.
  4MB chunk -> 2MB compressed -> upload 2MB -> store 2MB.
  50% bandwidth savings for text files.
  Not beneficial for already-compressed files (JPEG, MP4, PDF).
  Client detects file type and skips compression for binary formats.
```

### Concept 3: Storage Quota Enforcement

```
Each user has a storage quota (e.g., 15 GB free tier, 2 TB paid).

Tracking used storage:
  Table user_scores: storage_used (bytes). Updated on each file version commit.
  
  Challenge: chunk deduplication means two users sharing the same file should not
  both be charged the full file size. Options:
  
  Option A: charge each user the full logical size of their files.
    User A uploads 1GB file. Charged 1GB.
    User B uploads the same 1GB file. Charged 1GB.
    Both charged 1GB, but only 1GB stored.
    Simple to implement. Dropbox uses this model.
  
  Option B: charge users only for unique storage consumed.
    Complex: requires tracking which chunks each user "owns."
    If user A deletes their copy: do other users' quotas decrease?
    Not worth the complexity. Option A is correct for interviews.

Quota enforcement:
  On every upload commit:
    new_used = storage_used + file_version.total_size_bytes
    If new_used > storage_quota: reject with HTTP 507 Insufficient Storage.
    Else: UPDATE users SET storage_used = new_used WHERE user_id = ?

  On file deletion or version expiry:
    storage_used decreases by the deleted file's size.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+-----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)              | L6 (Staff)                     |
+---------------------+-----------------------------+--------------------------------+
| Chunking            | 4MB fixed chunks, SHA-256   | Rabin fingerprinting (variable |
|                     | per chunk, delta sync        | chunks), explains boundary-    |
|                     |                             | shift problem and why variable  |
|                     |                             | chunking solves it             |
+---------------------+-----------------------------+--------------------------------+
| Dedup               | "Same hash = one copy"      | Cross-user dedup privacy model |
|                     | basic explanation            | (check_chunks only returns      |
|                     |                             | "have it" for user's own        |
|                     |                             | uploads), ref counting for GC   |
+---------------------+-----------------------------+--------------------------------+
| Conflict resolution | Keep-both Dropbox model,    | Version vectors vs timestamps  |
|                     | mentions last-write-wins     | for conflict detection. Why    |
|                     | alternative                 | vector clocks are more accurate |
|                     |                             | than timestamps (clock skew).   |
+---------------------+-----------------------------+--------------------------------+
| Notification        | WebSocket for desktop,      | Long-poll vs SSE trade-offs.   |
|                     | APNs/FCM for mobile          | Shared folder fan-out math.    |
|                     |                             | Cursor-based fallback polling.  |
|                     |                             | Large group (1000 members) pull |
|                     |                             | vs push decision.              |
+---------------------+-----------------------------+--------------------------------+
| Resumable uploads   | Mentions chunking enables   | Full protocol: initiate session,|
|                     | resume from interrupted      | status check on reconnect,     |
|                     | upload                       | idempotent chunk upload,       |
|                     |                             | 24h session TTL, orphan GC.    |
+---------------------+-----------------------------+--------------------------------+
| Metadata sharding   | Knows DB needed, mentions   | Shards by user_id. Explains    |
|                     | Postgres                    | cross-shard queries (shared     |
|                     |                             | folders span user shards).     |
|                     |                             | Redesigns folder_members table  |
|                     |                             | to avoid cross-shard joins.    |
+---------------------+-----------------------------+--------------------------------+
| Bandwidth cost      | Mentions CDN for downloads  | Quantifies: LAN sync, CDN      |
|                     |                             | savings, compression strategy,  |
|                     |                             | $X/day/user cost model.        |
+---------------------+-----------------------------+--------------------------------+
| Client state machine| Knows client watches FS,    | 6-state machine with all       |
|                     | debounces, uploads only      | transitions. Race condition:   |
|                     | changed chunks              | MODIFIED_LOCAL + notification  |
|                     |                             | arriving simultaneously ->     |
|                     |                             | CONFLICT state handling.       |
+---------------------+-----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Dropbox Deduplication Privacy Vulnerability (2011)

**Company:** Dropbox  
**What happened:** Dropbox's deduplication implementation had a privacy flaw. The `check_chunks` API checked whether a chunk existed in the global chunk store — across ALL users. If user A knew the SHA-256 hash of a chunk in user B's private file, user A could call `check_chunks` with that hash and the server would respond "already have it." User A could then "add" the file to their drive without uploading it — essentially stealing it without possessing the actual bytes. A security researcher demonstrated this on publicly known files (DMCA-protected content).

**Root cause:** Cross-user deduplication without access control on the `check_chunks` endpoint. The server should only respond "have it" if the requesting user previously uploaded that chunk themselves.

**Fix:** Changed `check_chunks` to only return "already have it" if the user's own metadata references that chunk. Cross-user dedup still happens (the chunk is stored once), but it is invisible to the user. A user cannot "add" a file by hash without possessing the bytes.

**Staff lesson:** Content-addressed storage with cross-user deduplication creates privacy and copyright risks. The check endpoint must be scoped to the user's own history. Dedup savings are internal — the API surface must look like each user has their own independent storage.

---

### Incident 2: Dropbox Authentication Outage (2012)

**Company:** Dropbox  
**What happened:** Dropbox deployed a code change that accidentally removed authentication from their API. For approximately 4 hours, any user could access any other user's files without a password. The fix was to revert the change — but during those 4 hours, the sync protocol continued working (users happily syncing files), with no indication that authentication was disabled.

**Root cause:** The sync protocol continued working because it relied on OAuth tokens that were stored on devices. The authentication middleware was accidentally bypassed server-side, but client tokens still worked (they were simply not validated). Silent failure: no errors, no alerts, just missing security.

**Fix:** Added integration tests that explicitly test authentication failures (verify that requests without valid tokens are rejected). Added rate-of-change alerts: "if auth rejection rate drops to 0, something is wrong." Auth should reject a baseline of requests (scanners, expired tokens); zero rejections = suspicious.

**Staff lesson:** Monitoring must include negative assertions. If your auth system suddenly stops rejecting any requests, that is as alarming as a spike in failures. Test that security controls are actively enforced, not just that they do not break happy-path flows.

---

### Incident 3: Google Drive "Ghost Files" After Network Partition (2019)

**Company:** Google  
**What happened:** During a network partition in a Google datacenter, a subset of metadata write nodes became unreachable. Writes that were in-flight at partition time were applied to some replicas but not others. When the partition healed, both partitions had committed different versions of the same files for some users. Google Drive's conflict resolution merged these differently than the client expected, resulting in "ghost files" — files that appeared and disappeared depending on which metadata replica the user hit. Affected approximately 0.02% of users for 2 hours.

**Root cause:** Metadata writes were using asynchronous cross-datacenter replication. During the partition, writes that were "committed" on the primary were not yet replicated. On partition heal, the two-datacenter reconciliation logic had a bug in how it handled concurrent writes to the same file_id.

**Fix:** Switched file metadata writes to synchronous cross-datacenter replication for the primary + nearest replica pair. Introduced a reconciliation test suite that generates partition scenarios and verifies no ghost files. Added client-side fingerprint verification: after syncing, the client computes a hash of its local file state and compares to the server's expected hash.

**Staff lesson:** Metadata consistency is harder than chunk durability. Chunks are immutable and content-addressed (no conflicts possible). Metadata (version number, chunk list) is mutable and can conflict. Strong consistency for metadata writes is worth the latency cost. Asynchronous replication of mutable metadata across datacenters is a landmine.

---

### Incident 4: Box Runaway Sync Client Memory Usage (2021)

**Company:** Box  
**What happened:** A Box client update introduced a bug in the client-side debouncing logic. On macOS, FSEvents reported file changes not just for user files but also for temporary metadata files created by macOS itself (`.DS_Store` updates, Spotlight indexing temp files). The debounce filter was supposed to exclude these, but a regex bug let them through. The sync client entered an infinite loop: Box would ignore the `.DS_Store` sync (correctly), but macOS's response to Box's file access itself triggered another FSEvents change, which triggered another sync check. Box's client process grew to 4 GB RAM and pegged one CPU core at 100%. Users noticed their laptop fans running constantly and battery draining in 2 hours.

**Root cause:** Sync loop triggered by the sync client's own file access events. The client was not excluding its own writes from the inotify/FSEvents watch. Debounce filter had a regex bug (`\.DS_Store` written as `\.DS_Store.*` which matched correctly but excluded a needed case).

**Fix:** Added an explicit exclusion list for files created by macOS system processes. Added client-side rate limiting: if more than 100 sync events are triggered in 1 second for the same directory, back off for 10 seconds (circuit breaker for sync loops). Added telemetry: if RAM > 500 MB for the sync process, trigger an alert and a diagnostic report.

**Staff lesson:** File system watchers must exclude the sync client's own writes and OS metadata files. A sync client that can trigger an infinite loop via its own file access is a reliability bug, not a performance bug. Include rate limiting and circuit breakers in the sync loop, not just in the upload pipeline.

---

### Incident 5: iCloud Drive Conflict Storm at iOS Update Release (2023)

**Company:** Apple  
**What happened:** When iOS 17 was released, hundreds of millions of devices updated simultaneously within 24 hours. The iOS update modified dozens of system files in the iCloud container (preferences, app state files). These were detected as "local changes" by the iCloud sync daemon. For users with the same files on macOS and iPhone, the iOS update caused mass conflicts: macOS had version X of the plist files, iOS just created version Y (post-update). iCloud's conflict resolution created millions of conflict copies (`plist (iPhone's conflicted copy).plist`), filling many users' iCloud drives with garbage files.

**Root cause:** iOS update process did not suppress iCloud sync notifications during the update. Files modified by the OS installer should not have been treated as user edits. The conflict copy logic did not distinguish "OS-generated file" from "user-edited file."

**Fix:** Added an "update mode" flag to iOS update installer: while in update mode, suppress all iCloud sync triggers for system-owned files. Added a filter: files in system-managed paths (outside the user's Documents folder) are not synced by iCloud. Added conflict copy rate limiting: if a single device generates more than 50 conflict copies in 5 minutes, suppress further conflict copies and log for investigation.

**Staff lesson:** Sync systems must distinguish user-intent file changes from system-generated file changes. The OS installer, antivirus software, and backup tools all write files without user intent. Sync daemons that cannot distinguish these sources will create spurious conflicts at scale. Rate limiting on conflict copy creation prevents a bad edge case from filling users' storage.

---

## Exercises

### Exercise 1: Chunking a File

**Problem:** A user has a 20MB text document. They add 500 bytes at position 2,500,000 (halfway through the first 4MB chunk). With fixed 4MB chunking, how many chunks change? How many bytes are uploaded? Compare with variable-length (Rabin) chunking where only the "affected region" is re-chunked.

**Solution:**

```
Fixed 4MB chunking:
  Original file: 20MB -> 5 chunks of 4MB each
  Chunks: [0-4MB], [4-8MB], [8-12MB], [12-16MB], [16-20MB]

  After inserting 500 bytes at position 2.5MB:
    File size: 20MB + 500 bytes = 20,000,500 bytes
    New chunk boundaries:
      Chunk 0: bytes 0 to 4,194,303 (includes the 500-byte insert)
        NEW SHA-256 (insertion changed content of this chunk)
      Chunk 1: bytes 4,194,304 to 8,388,607
        NEW SHA-256 (shifted by 500 bytes relative to before)
      Chunk 2: bytes 8,388,608 to 12,582,911
        NEW SHA-256 (shifted by 500 bytes)
      Chunk 3: bytes 12,582,912 to 16,777,215
        NEW SHA-256 (shifted by 500 bytes)
      Chunk 4: bytes 16,777,216 to 20,000,499
        NEW SHA-256 (shifted by 500 bytes)
    
    All 5 chunks changed! 500-byte insertion causes 20MB re-upload.
    This is the boundary-shift problem.

Variable-length (Rabin) chunking:
  Original: fingerprinting produces chunk boundaries at content-dependent positions.
  Example boundaries: [0-3.9MB], [3.9-7.8MB], [7.8-11.9MB], ...
  These are determined by hash patterns in the content.

  After inserting 500 bytes at position 2.5MB:
    Chunk 0 (0 to first fingerprint hit): CHANGED (insertion is in this region).
      The fingerprint hit position shifts slightly: ~3.9MB boundary moves to ~3.900500MB.
      Or may stay at ~3.9MB if the fingerprint hit is downstream of the insert.
      Either way: chunk 0 changes.
    
    After the first fingerprint hit (~3.9MB), the content is IDENTICAL to the original
    (just shifted by 500 bytes, but fingerprinting looks at content patterns).
    The subsequent fingerprint hits occur at the same CONTENT as before.
    Chunks 1, 2, 3, 4: UNCHANGED hash.
  
  Result: 1 chunk changed (~4MB) vs 5 chunks (20MB) with fixed chunking.
  Upload savings: 80% bandwidth reduction for an insertion at the beginning of a file.
```

---

### Exercise 2: Conflict Detection

**Problem:** Two devices share a file "notes.txt" at version 7. Device A edits offline and submits with `base_version=7`. Device B also edits offline and submits with `base_version=7`. Device A's upload arrives first and is committed as version 8. Device B then submits. What does the server do? Write the conflict detection logic and the conflict copy creation logic.

**Solution:**

```
Device A's upload arrives:
  POST /files/commit
  {file_id: "notes_123", base_version: 7, chunk_list: [...A's chunks...], device_id: "device_A"}
  
  Server check: SELECT version FROM file_versions WHERE file_id='notes_123' ORDER BY version DESC LIMIT 1
  Current version: 7. base_version = 7. 7 == 7. No conflict.
  INSERT INTO file_versions (file_id, version, chunk_list, ...) VALUES ('notes_123', 8, [...A's...], ...)
  Commit: version 8 is now latest. Return: {version: 8, status: "committed"}

Device B's upload arrives:
  POST /files/commit
  {file_id: "notes_123", base_version: 7, chunk_list: [...B's chunks...], device_id: "device_B"}
  
  Server check: SELECT version FROM file_versions WHERE file_id='notes_123' ORDER BY version DESC LIMIT 1
  Current version: 8. base_version = 7. 8 != 7. CONFLICT.

Conflict resolution:
  1. Do NOT overwrite version 8 (Device A's changes would be lost).
  2. Create a conflict copy:
     a. Generate new file_id: "notes_conflict_456"
     b. Insert new file record:
        INSERT INTO files (file_id, owner_user_id, folder_id, filename)
        VALUES ('notes_conflict_456', owner, folder_id, 'notes (Device B conflicted copy 2024-12-24).txt')
     c. Insert file version for the conflict copy:
        INSERT INTO file_versions (file_id, version, chunk_list, ...)
        VALUES ('notes_conflict_456', 1, [...B's chunks...], ...)
  3. Return to Device B:
     {status: "conflict", conflict_copy_file_id: "notes_conflict_456", conflict_copy_filename: "..."}
  4. Publish two sync events to Kafka:
     - Event for "notes.txt": other devices pull version 8 (Device A's version).
     - Event for "notes (Device B conflicted copy...).txt": all devices download the conflict copy.

Result on each device:
  Device A: "notes.txt" at version 8 (its own version, already has it).
             "notes (Device B conflicted copy 2024-12-24).txt" appears (new file sync'd).
  Device B: "notes.txt" downloads version 8 (Device A's version replaces B's local edit).
             "notes (Device B conflicted copy 2024-12-24).txt" appears (B's version preserved).
  Other devices: both files sync'd.
```

---

### Exercise 3: Bandwidth Math

**Problem:** Your file sync service has 10M DAU. Each user makes on average 3 file edits per day. The average file size is 2MB, and on each edit, 25% of the file changes (delta). What is the total upload bandwidth per second? What is the total download bandwidth (assuming each user has 2 other devices that sync)?

**Solution:**

```
Upload bandwidth:
  Edits per day: 10M users * 3 edits = 30M edits/day
  Average delta per edit: 2MB * 25% = 0.5MB = 512 KB
  Total upload volume/day: 30M * 512 KB = 15 TB/day
  Upload bandwidth: 15 TB / 86400s = 173,611 MB/s = 165 GB/s

  Wait, let's re-check: 30M edits * 0.5 MB = 15,000,000 MB = 15 TB/day
  Per second: 15 * 10^12 bytes / 86400 s = 173.6 * 10^6 bytes/s = 165.5 MB/s
  
  In Gbps: 165.5 MB/s * 8 = 1.3 Gbps of upload bandwidth.
  (Manageable. A single 10 Gbps network link handles this with 87% headroom.)

Download bandwidth:
  Each edit triggers downloads on 2 other devices.
  Download volume per edit: same delta = 512 KB per device.
  Total download volume/day: 30M edits * 2 devices * 512 KB = 30 TB/day
  Download bandwidth: 30 TB / 86400s = 347 MB/s = 2.6 Gbps

  With CDN (80% cache hit rate for shared files):
  Unique origin download: 20% * 30 TB = 6 TB/day from origin servers.
  CDN delivers: 24 TB/day from edge.
  
  Origin bandwidth: 6 TB / 86400s = 69.4 MB/s = 0.5 Gbps from origin.
  Significant savings.

Total bandwidth: 165 MB/s upload + 347 MB/s download = 512 MB/s = 3.9 Gbps peak.
This is realistic for a 10M DAU service. Scale to 50M DAU: 19.5 Gbps total.
```

---

## Homework

**Short 1:** Open Dropbox (or Google Drive) and deliberately create a conflict. Disconnect from the internet on your laptop, edit a text file. On your phone (also offline), edit the same file. Then connect both devices. What happens? Does Dropbox create a conflict copy? Does Google Drive? How does each service name the conflict copy?

**Short 2:** Compute the SHA-256 hash of a file on your computer (on macOS: `shasum -a 256 filename`). Edit the file by adding one character. Compute the hash again. How different are the two hashes? What does this tell you about why SHA-256 can serve as a fingerprint for detecting changes?

**Short 3:** Read about inotify (Linux) or FSEvents (macOS). What events are emitted when you: (a) save a file in a text editor, (b) move a file from one folder to another, (c) copy a file, (d) rename a file? Which events does the Dropbox client need to listen for to detect all possible file changes?

**Deep 1:** Implement a basic file sync client in Python:
- Watch a local directory for changes (use `watchdog` library on Python)
- Split changed files into 4MB fixed chunks
- Compute SHA-256 hash per chunk
- Maintain a local state file (JSON): `{path: [hash0, hash1, ...], version: N}`
- On change: compare new hashes with stored state. Print "upload chunk X" for changed chunks only.
Test with: small edits, large insertions at the beginning vs end of a file. Observe how many chunks change in each case.

**Deep 2:** Read Dropbox's 2012 blog post "How We've Scaled Dropbox" and their paper "Magic Pocket" (2016). What storage backend did they build to replace S3? What deduplication system do they describe? How did they achieve 11 nines of durability without paying AWS S3 pricing?

---

## Glossary

**Chunk:** A fixed-size (typically 4MB) or variable-size segment of a file used for delta sync. Each chunk is independently identified by its SHA-256 hash and stored as a separate object in the chunk store.

**Delta sync:** The practice of uploading and downloading only the changed chunks of a file rather than re-uploading the entire file on every change. Reduces bandwidth by 70-90% for typical edits.

**Content-addressed storage:** A storage system where objects are identified by the hash of their contents, not by an assigned name or path. The same content always maps to the same key; different content always maps to a different key.

**Deduplication:** The elimination of redundant copies of data. In file sync, if two users upload the same chunk (same content, same SHA-256 hash), only one copy is stored. Both users' metadata records reference the same chunk.

**Conflict copy:** A copy of a file created by the sync service when two devices have made conflicting edits to the same file since their last common version. Typically named with the device and date: "report (Jane's conflicted copy 2024-12-24).docx."

**Version vector:** A data structure tracking how many updates each device has made to a file. Used to detect concurrent edits (conflicts) more accurately than timestamps. Two version vectors are concurrent (conflict) if neither dominates the other.

**Boundary shift problem:** In fixed-size chunking, inserting or deleting content at the beginning of a file shifts all subsequent chunk boundaries, causing all chunks to have new hashes even if their content is effectively unchanged.

**Rabin fingerprinting:** A content-defined chunking algorithm that determines chunk boundaries based on the rolling hash of recent bytes, not position. Solves the boundary shift problem: insertions only affect the "region" around the insertion.

**FSEvents (macOS) / inotify (Linux):** OS-level APIs for receiving notifications when files and directories change. Used by sync clients to detect when a user has edited a file without polling the file system.

**Resumable upload:** An upload protocol that can be interrupted and resumed without starting over. Implemented via upload sessions: the server tracks which chunks have been received; the client queries the session state on reconnect and sends only missing chunks.

**Long poll:** An HTTP technique where the client sends a request and the server holds it open (up to 30-60 seconds) until an event occurs or a timeout fires. Used for real-time notifications when WebSockets are unavailable.

**Cursor-based sync:** A sync protocol where each client maintains a "cursor" (opaque token representing a point in the sync history) and can request all changes since that cursor. Provides reliable eventual consistency even when push notifications are lost.

---

## The One-Sentence Summary

> "File sync = split each file into 4MB chunks (SHA-256 per chunk) for delta sync (upload only changed chunks) + content-addressed chunk store (identical chunks stored once for dedup) + metadata DB recording the ordered chunk list per file version + WebSocket push (with cursor-based poll fallback) to notify other devices — the core insight is that re-uploading the full file on every edit is catastrophically wasteful, so chunking turns a 10MB file update into a 4MB chunk upload 90% of the time, and the same hashing-based approach enables cross-user deduplication, resumable uploads, and corruption detection for free."

---

## Interview Q&A — Most Common Cross-Questions

---

**Q1: Why chunk the file at all? Why not just compute a hash of the full file and only re-upload if the file changed?**

The full-file hash tells you the file changed, but it tells you nothing about what changed. Without chunking, you must upload the entire file whenever any byte changes. For a 1GB video file where someone corrected a typo in embedded metadata, that's 1GB uploaded for a 1KB change. Chunking lets you identify which 4MB sections changed and upload only those. It also enables deduplication at the chunk level — two different files sharing common paragraphs (a template body, for example) share those chunks in storage. The SHA-256 per-chunk approach gives you delta sync, deduplication, and resumability all from the same mechanism.

---

**Q2: How does the server know which chunks it already has? Doesn't the check_chunks API require reading a huge index?**

The chunk store is content-addressed: the S3 key is the SHA-256 hash itself. Checking whether a chunk exists is a HEAD request to S3 with that key — a pure key lookup, O(1). The client sends a list of chunk hashes to check, and the server does N parallel HEAD requests to S3. Since S3 is designed for billions of objects with O(1) key lookups, checking 10 chunk hashes takes 10-20ms pipelined. No secondary index or scan required.

---

**Q3: How do you handle a very large file — say, 10GB? What if the upload is interrupted halfway?**

A 10GB file splits into 2,500 chunks of 4MB each. The client initiates an upload session with the server (gets a session_id), then uploads chunks concurrently (multiple parallel uploads). The server marks each chunk received in Redis with a 24-hour TTL. If the network drops mid-upload, the client reconnects, queries the server for which chunks were received, and resumes uploading only the missing ones. Each chunk is idempotent (same SHA-256 always produces the same key in S3), so re-uploading a chunk that was partially received is safe. The file is not committed to the user's metadata until all chunks are confirmed.

---

**Q4: What happens when two devices edit the same file offline? How does the server detect and resolve the conflict?**

Each upload includes a `base_version` field — the version the edit was based on. When device B uploads, the server checks: is `base_version` still the current latest version? If device A already committed a new version (say, version 8) and device B's `base_version` is 7, the server knows they edited concurrently. Resolution: the server creates a conflict copy — a new file with a name like "report (Device B's conflicted copy 2024-12-24).docx" — containing device B's version. Device A's committed version remains as the canonical "report.docx." Both devices sync both files. The user manually resolves which version to keep.

---

**Q5: Why keep-both instead of automatically merging the conflicting edits?**

Automatic merging requires understanding the file's internal format. A text file can be merged with a three-way diff (base + both edits → merged result). But a Word document, an Excel spreadsheet, or a Photoshop file has a binary format that a generic sync service cannot parse and merge. Dropbox's approach (keep-both) works for any file type with no format knowledge required. It also never silently loses data — the user's edit always appears somewhere. The downside is that the user must manually merge, which is annoying for frequent conflicts. Google Docs handles this differently by making the document format CRDT-friendly (operational transforms), but that requires Google to control the file format — not feasible for a general-purpose file sync service.

---

**Q6: How does device B know to sync when device A uploads a file? What if device B is offline?**

For connected desktop clients: a WebSocket connection is maintained between the client and the Notification Service. When device A uploads, the Upload Service publishes an event to Kafka. The Notification Service consumes it and pushes a message to device B's WebSocket connection. The message contains the file_id and new version — device B then downloads the changed chunks.

For offline or mobile clients: when device B comes online, it sends a request to the sync API with its last-known cursor (a timestamp or sequence number). The server returns all changes since that cursor. This cursor-based polling is the reliability guarantee — push notifications are a fast-path optimization, not a correctness requirement.

---

**Q7: What is content-addressed storage and why is it used here?**

Content-addressed storage means an object's storage key is derived from its content, not assigned. Here, the key is the SHA-256 hash of the chunk's bytes. Two identical chunks from different files or users always produce the same hash, so they map to the same key — only one copy is stored. This achieves deduplication automatically without any dedup logic: the storage layer simply cannot hold two different objects with the same key. It also makes uploads idempotent: uploading the same chunk twice is a no-op (the second write goes to the same key and finds the bytes already there). The immutability is a bonus: a chunk with a given hash is write-once, making it safe to cache forever at CDNs.

---

**Q8: What is the boundary shift problem and how do variable-length chunks help?**

With fixed 4MB chunks, chunk boundaries are at positions 0, 4MB, 8MB, 12MB, etc. If a user inserts 1 byte at position 1MB, every chunk after that has its content shifted by 1 byte. All shifted chunks have new SHA-256 hashes — even though bytes 5MB onward are identical to before. The entire file must be re-uploaded. Variable-length chunking (Rabin fingerprinting) defines chunk boundaries based on a rolling hash of recent bytes. After a 1MB insertion, the rolling hash eventually finds the same pattern in the original content and "resynchronizes" to the same boundary. All chunks after the resynchronization point are unchanged. Typically only 1-2 chunks change even for large insertions, regardless of insertion position.

---

**Q9: How does deduplication work across users? Isn't it a privacy concern?**

The dedup is internal: the same chunk is stored once in S3, but each user's metadata record independently lists their chunk hashes. Deduplication is invisible to users. The privacy concern is in the `check_chunks` API: if the server replies "I already have this chunk" to any user who asks, a malicious user could prove that a specific file exists in the system (or in another user's drive) by sending the expected chunk hashes. The fix: `check_chunks` only returns "already have it" if the requesting user's own metadata previously referenced that chunk. This prevents cross-user hash probing while maintaining the storage deduplication benefit.

---

**Q10: How do you shard the metadata database? What is the hotspot risk?**

Shard by `owner_user_id`. All of a user's file metadata (files, versions, folder structure) is on one shard, so queries like "list all my files" need no cross-shard joins. With 8 shards, each handles 500M/8 = 62.5M users. The hot user risk: if one user has terabytes of files with millions of versions (an enterprise with 10,000 active files and 30 days of history), a single shard bears the load of that enterprise. Mitigate by: increasing the number of shards (reduces the blast radius), moving large users to a dedicated shard (manual rebalancing), or caching the most-queried metadata in Redis so not every file list request hits the DB.

---

**Q11: What happens to storage when a user deletes a file?**

Deletion is a soft delete: set `is_deleted = true` on the file record, which hides it from the user's file list but retains all versions for 30 days (deleted file recovery). After 30 days: hard delete the file record and all version records. The chunk references are decremented via a background GC job. A chunk is deleted from S3 only when its reference count reaches 0 AND it has not been referenced by any active file for 7 days (the buffer prevents a race where a new file is concurrently created with the same chunk). Storage quota is reclaimed at soft delete time (the user's `storage_used` decreases immediately even though the data is retained for 30 days).

---

**Q12: How would you handle a shared folder with 1,000 members? Fan-out to 1,000 users per file change?**

At 1,000 members and 11,000 file changes per second: 11M notifications per second for this single folder alone — not feasible to push-notify all members instantly. Switch from push to pull for large groups: members of folders with more than, say, 100 members use a cursor-based poll model (poll every 30 seconds for changes). This limits the notification fan-out to the polling rate. Alternatively: batch changes per user and send one notification every 5 seconds (collapses 100 changes into one poll trigger). Push is reserved for small groups (under 100 members) where low-latency sync matters; pull provides the same eventual consistency for large groups at a fraction of the fan-out cost.

---

**Q13: What is an upload session and why does it use Redis?**

An upload session is server-side state tracking which chunks of a large upload have been received. It is created at upload initiation and contains: the file_id, expected chunk count, and a set of received chunk indices. When the client asks "which chunks do you have?" the server consults this session state. Redis is used (not the DB) because: (1) session state is ephemeral (24-hour TTL), (2) it needs fast writes (marking chunks received in real-time), and (3) Redis SADD + SMEMBERS operations are O(1) and O(N) respectively — trivial for a set of 2,500 chunk indices. Using the DB for this would create write-hot rows (every chunk upload updates the same row) and would complicate cleanup.

---

*Section 5 — L5 / Senior SWE. Frequently asked at Dropbox, Google, Box, Notion. Distinct from Ch52 (Object Storage API). Pairs with Ch61e (Key-Value Store for chunk metadata) and Ch60 (Real-Time Chat for WebSocket notification patterns).*

---

**Q14: How do you handle a shared folder where two users edit the same file simultaneously on different devices?**

This is the conflict detection and resolution problem. The system detects a conflict when it receives two uploads of the same file with no linear version history — Device A's version and Device B's version are both descended from the last common ancestor version, with no ordering between them (concurrent edits, not sequential).

Detection uses version vectors: each device maintains a version vector `{device_id → logical_clock}`. File metadata stores the last-known version vector. When Device A uploads version N+1 (with its own version vector advanced), the server checks: is Device A's version vector a superset of the file's current version vector? If yes — linear update. If no — concurrent edit detected.

Resolution strategies: (1) Keep-both (Dropbox default): create "filename (Bob's conflicted copy 2024-12-24).docx" as a sibling file. The original file keeps whichever version arrived first. Both versions are preserved on disk. Users manually merge. (2) Last-write-wins: always accept the newer upload timestamp. Risk: silent data loss. (3) CRDT-based merge: for files with CRDT structure (like Notion's content, Google Docs' operational transforms). Automatically merges changes at the character/operation level with no conflicts. Requires format-specific merge logic.

Dropbox uses keep-both because it works for all file types (binary files, Office documents, PDFs) without requiring format-specific knowledge. The downside: if both users are editing actively, they accumulate many conflict copies.

---

**Q15: How do you handle storage quotas — preventing users from exceeding their 15 GB free limit?**

The quota is tracked in the `users` table: `storage_used_bytes BIGINT`. Every successful chunk upload increments this: `UPDATE users SET storage_used_bytes = storage_used_bytes + chunk_size WHERE user_id = ?`. Before allowing a new upload, check: `SELECT storage_used_bytes FROM users WHERE user_id = ?` and reject if `storage_used_bytes + estimated_upload_size > quota`.

Race condition: two concurrent uploads both read storage_used_bytes = 14.9 GB. Both calculate they'll fit (14.9 + 0.5 = 15.4 GB, rejected; but if quota is 15 GB and each upload is 0.2 GB: both check and pass, both succeed → 15.3 GB stored). Fix: use an atomic `UPDATE users SET storage_used_bytes = storage_used_bytes + chunk_size WHERE user_id = ? AND storage_used_bytes + chunk_size <= quota`. Check rows_affected=1. If 0, quota exceeded.

Deduplication interaction: if a user uploads a chunk that already exists in the system (same SHA-256 hash), the chunk is not stored again. But the user's quota is still charged for the logical file size — otherwise users could collude to "share" storage without paying for it. Quota is based on logical file bytes owned, not physical storage bytes consumed.

Soft vs hard quota: at 95% full, send a warning email. At 100%, reject new uploads (but allow downloads — never make data inaccessible due to quota). Allow 7-day grace period at 100%+overflow for files that were mid-upload when quota was hit.

---

## Monitoring and Observability

### Key Metrics by Subsystem

**Upload pipeline:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `upload_throughput_MB_per_sec` | varies | Drop > 50% sustained (S3 degraded, bandwidth exhaustion) |
| `chunk_dedup_rate_%` | 20–40% | < 5% (dedup not working — investigate content hash check) |
| `upload_session_create_rate` /sec | varies | Spike > 10× (mass re-upload event — check for client bug) |
| `chunking_latency_p99_ms` | < 500ms | > 2,000ms (client CPU bottleneck on large files) |
| `s3_put_latency_p99_ms` | < 200ms | > 1,000ms (S3 regional issue) |

**Sync notification:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `notification_delivery_latency_p99_ms` | < 1,000ms | > 5,000ms (Kafka consumer lag, WebSocket pool overloaded) |
| `websocket_connection_count` | grows linearly with users | Drop > 20% sudden (mass disconnect event) |
| `cursor_poll_rate` /sec | low baseline | Spike (clients falling back to polling — WebSocket tier down) |
| `notification_delivery_failure_rate_%` | < 0.1% | > 1% (offline devices not receiving) |

**Metadata database:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `metadata_query_latency_p99_ms` | < 10ms | > 50ms (shard hot spot or index missing) |
| `conflict_rate` per hour | 0–100 | > 10,000 (surge in concurrent edits — shared folder storm) |
| `shard_size_GB` per shard | < 500 GB | > 1 TB (rebalancing needed) |
| `gc_chunk_delete_rate` /hour | 100–1,000 | > 100,000 (mass deletion event — check for runaway GC) |

**Storage (S3):**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `orphan_chunk_count` (in S3 but no metadata reference) | < 1,000 | > 100,000 (GC falling behind) |
| `storage_cost_per_user_month` | < $0.02 | Spike > 2× (dedup not working, large files uploaded) |
| `s3_request_rate` /sec | varies | > 100K (request rate limit approaching — split prefixes) |

### Distributed Trace: File Upload Flow

```
Trace: upload_file (file_id = new_file_id)
  ├─ Span 1: client_chunking (compute SHA-256 per 4MB chunk)   200ms per GB
  ├─ Span 2: check_chunks (POST /chunks/check)                  10ms
  ├─ Span 3: upload_chunks (PUT /chunks/{hash} per new chunk)   per chunk
  │         ├─ Span 3a: s3_put (upload to S3)                  50ms avg
  │         └─ Span 3b: metadata_insert (record chunk in DB)    5ms
  ├─ Span 4: finalize_file (POST /files/{id}/commit)            15ms
  │         ├─ Span 4a: metadata_update (file + version)        8ms
  │         └─ Span 4b: kafka_publish (file_changed event)      5ms
  └─ Span 5: notification_fanout (WebSocket push to devices)    20-500ms
```

Alert on: Span 3a p99 > 1,000ms (S3 slow), Span 5 > 5,000ms (notification fan-out blocked), conflict detected in Span 4a (log for UX tracking).

---

## Capacity Planning — Dropbox at 500M Users

**Assumptions:** 500M registered users, 50M daily active users, 2 uploads/user/day average, average file 5 MB.

**Upload volume:**
```
50M DAU × 2 uploads/day = 100M file uploads/day
100M / 86,400 sec = 1,157 uploads/sec
Average file 5 MB / 4 MB chunk size = 1.25 chunks per file
1,157 uploads/sec × 1.25 chunks = 1,446 chunk uploads/sec
With 30% dedup rate: 1,446 × 0.7 = 1,012 new S3 PutObjects/sec
```

**S3 storage:**
```
1,012 new chunks/sec × 4 MB/chunk = 4,048 MB/sec = ~3.5 TB/day added to S3
Monthly storage growth: 3.5 TB × 30 = 105 TB/month
At $0.023/GB/month: $2,415/month for new storage (not counting existing)
Total at 500M users × 15 GB average: 7.5 PB → $172,500/month for stored data
```

**Metadata database:**
```
500M users × 15 GB / 4 MB = 1.875B chunks per user = impossible per user
Realistic: 500M users × 1,000 files avg × (1 row/file + 10 chunk refs/file) = 5.5B rows
5.5B rows × 200 bytes avg = 1.1 TB metadata
8 PostgreSQL shards: 1.1 TB / 8 = 137 GB/shard (comfortable with 512 GB RAM)
```

**Notification fan-out:**
```
100M file changes/day = 1,157 changes/sec
Each change notifies avg 2.3 devices per user = 2,662 notifications/sec
WebSocket tier: if each server handles 100K connections: 50M active connections / 100K = 500 servers
Push rate: 2,662 pushes/sec over 500 servers = 5.3 pushes/sec/server → trivial
```

**Bandwidth:**
```
Upload: 1,012 chunks/sec × 4 MB = 4 GB/sec = 32 Gbps upload bandwidth
Download: assume 3:1 download to upload = 96 Gbps download bandwidth
CDN: hot files cached at CDN (recent file changes) — CDN absorbs 80% of download → 19 Gbps to origin
```

---

## Common Anti-Patterns

**Anti-pattern 1: Not deduplicating before uploading (always uploading all chunks)**

Fix: `check_chunks(hashes)` first. Upload only the ones the server says it doesn't have. This is the delta sync mechanism that makes Dropbox efficient. Uploading a 1 GB file where only 4 MB changed should result in uploading exactly 4 MB, not 1 GB.

**Anti-pattern 2: Using mutable storage keys (content overwritten on update)**

Fix: content-addressed storage. Key = SHA-256 of chunk bytes. Old chunks are never overwritten — new versions create new chunk hashes, and metadata records which chunks make up each version.

**Anti-pattern 3: Storing the full file in S3 per version (no chunking)**

Fix: Chunking with deduplication. A 1 GB file has 256 chunks. Each edit changes 1 chunk. Only 1 new chunk per edit is stored. After 10 edits: 256 + 10 = 266 chunks stored, not 2,560.

**Anti-pattern 4: Per-device WebSocket without a fallback cursor**

Fix: Every push notification contains a sequence number. On reconnect, the client sends its last-seen sequence number. The server returns all events since that sequence number (cursor-based polling). WebSocket is the fast path; cursor polling is the reliability guarantee.

**Anti-pattern 5: Synchronous file metadata update in the upload hot path**

Fix: chunk uploads go directly to S3. Metadata is written asynchronously via Kafka. The `finalize_file` API call (after all chunks are uploaded) writes the complete file record in one transaction. The chunk-level metadata writes are batched, not per-chunk.

**Anti-pattern 6: Deleting chunks immediately on file delete (breaks references)**

Fix: Reference counting. Only delete a chunk from S3 when its reference count drops to 0 AND a 7-day grace period has passed (prevents race with concurrent file creation using the same chunk). Use a GC job, not synchronous deletion.

---

## Production Incident Deep Dives (Extended)

### Incident 6: Google Drive Collaboration Storm — Shared Document Notification Loop (2020)

**Date:** Q1 2020 (remote work surge during COVID-19)
**Duration:** 3 hours of degraded notification delivery

**What happened:** With the surge in remote work, Google Drive's use of shared folders increased dramatically. A large enterprise with 5,000 employees in a single shared folder began experiencing an exponential notification fan-out problem. Every file edit triggered a notification to all 5,000 members. Each notification arrival caused the Drive desktop client to poll for recent changes (the client treated notifications as a trigger to check-in, not as the authoritative list of changes). 5,000 clients × 1,000 file edits/hour = 5M polling requests/hour for a single folder.

Across 50 such large enterprise folders: 250M notification-triggered poll requests/hour — overwhelming the metadata service.

**Root cause:** Notification model treated push notifications as "something changed, go check what" (trigger model) instead of "here is exactly what changed" (data model). Trigger model causes every notification to fan-out into a database read per recipient.

**Fix:**
1. **Rich notifications:** include the delta in the notification itself (which file changed, which version). Client processes the notification directly without making a polling request.
2. **Fan-out limits for large shared folders:** folders with > 500 members use a pull model (member clients poll every 60 seconds instead of receiving push per change). Aggregate notification: "37 files changed in the last 60 seconds — here is the summary."
3. **Coalescing:** multiple file changes within a 5-second window are grouped into one notification. Reduces notification count by 5-10× during heavy editing sessions.

---

## Additional Exercises

### Exercise 4: Quota-Aware Upload with Atomic Check

**Problem:** A user with 14.8 GB used wants to upload a 500 MB file. Their quota is 15 GB. Design the quota check to prevent exceeding the limit even with concurrent uploads.

**Solution:**

```sql
-- Attempt quota-aware atomic upload commit:
-- Called at finalize_file, when we know the total size of all new chunks

BEGIN;

-- Step 1: Compute total new bytes this upload adds (chunks not already referenced by this user)
SELECT COALESCE(SUM(c.size_bytes), 0) as new_bytes
FROM file_chunks fc
JOIN chunks c ON fc.chunk_hash = c.sha256_hash
WHERE fc.file_id = :new_file_id
  AND c.sha256_hash NOT IN (
      SELECT fc2.chunk_hash FROM file_chunks fc2
      JOIN files f2 ON fc2.file_id = f2.file_id
      WHERE f2.owner_user_id = :user_id AND f2.is_deleted = false
  );
-- Assume result = 512 MB (some chunks are new, some deduped from existing files)

-- Step 2: Atomic quota check + increment
UPDATE users
SET storage_used_bytes = storage_used_bytes + :new_bytes  -- 512 MB
WHERE user_id = :user_id
  AND storage_used_bytes + :new_bytes <= quota_bytes;     -- 15,360 MB limit

-- rows_affected = 1 → success, commit
-- rows_affected = 0 → over quota, rollback

IF rows_affected = 0:
    ROLLBACK;
    RETURN 413 "Quota exceeded. Used: 14,848 MB, Limit: 15,360 MB, Upload: 512 MB"

-- Step 3: Commit the file record
INSERT INTO files (file_id, owner_user_id, name, ...) VALUES (...);
COMMIT;
```

---

### Exercise 5: Version History and Point-in-Time Recovery

**Problem:** A user accidentally saves over an important file and wants to restore the version from 3 days ago. Design the data model and API for version history and point-in-time restore.

**Solution:**

```sql
-- Data model (already shown in chapter, extended here):
CREATE TABLE file_versions (
  version_id     BIGSERIAL PRIMARY KEY,
  file_id        UUID NOT NULL,
  version_number INT NOT NULL,
  chunk_hashes   TEXT[],          -- ordered array of SHA-256 hashes
  size_bytes     BIGINT,
  created_at     TIMESTAMP NOT NULL,
  created_by     BIGINT,          -- user_id
  device_id      UUID,
  change_summary VARCHAR(200),    -- optional: "Added 3 paragraphs"
  UNIQUE (file_id, version_number)
);

-- List version history:
GET /files/{file_id}/versions
Response:
[
  {"version": 23, "size_bytes": 48291, "created_at": "2024-12-24T14:00:00Z", "created_by": "Alice"},
  {"version": 22, "size_bytes": 47100, "created_at": "2024-12-21T09:30:00Z", "created_by": "Alice"},
  ...
]

-- Restore a version:
POST /files/{file_id}/restore
Body: {"version_number": 20}

Server-side:
  1. Read file_versions WHERE file_id=? AND version_number=20 → get chunk_hashes
  2. All chunks already exist in S3 (chunks are immutable, never deleted while referenced)
  3. Create a new file_version row with these same chunk_hashes and version_number=24
  4. Update files.current_version_id = new_version_id
  5. Publish file_changed event to Kafka
  6. All devices sync to version 24 (which happens to have version 20's content)
  
Note: the restore creates a new version (not overwriting history). The history is preserved:
  v20: original content
  v21: accidental overwrite
  v22, v23: more edits on top of overwrite
  v24: restored from v20 (new version, same chunk_hashes as v20)
This makes restore operations safe and auditable.
```

---

## L5 vs L6 Calibration Table — File Sync Service

| Topic | L5 Answer | L6/Staff Answer |
|-------|-----------|-----------------|
| Chunking | 4 MB fixed chunks; SHA-256 per chunk; skip existing chunks at upload | Plus: Rabin fingerprinting for content-based chunking (boundary shift problem); chunk size optimization (small files: 1 chunk; large files: 4 MB; tuning based on file type) |
| Conflict resolution | Keep-both approach; version vectors for concurrent edit detection | Plus: operational transformation (OT) for text-based collaborative editing; CRDT for conflict-free concurrent edits; format-specific merge (Excel cell-level, code line-level) |
| Notification | WebSocket push + cursor-based pull fallback; Kafka fan-out | Plus: exponential backoff + jitter for reconnect storms; push-only for small groups (< 100), pull-only for large groups (> 1K); prioritized notification delivery (your own edits confirmed first) |
| Storage dedup | Content-addressed chunks (key = SHA-256); reference count GC | Plus: cross-user dedup with privacy-safe hash probing (only confirms chunk exists if the requesting user already owns it); CDC (change data capture) for GC to avoid full table scans |
| Metadata sharding | Shard by owner_user_id; 8 shards for 500M users | Plus: hotspot mitigation for enterprise users (dedicated shard); directory-level metadata cache (Redis hash per folder); consistent hashing with virtual nodes for rebalancing |
| Quota enforcement | Atomic UPDATE WHERE storage_used + size <= quota; rows_affected check | Plus: quota enforcement at chunk upload time (not just finalize) to fail fast; soft quota with 7-day grace; per-folder quota for team shared spaces |
| Version history | file_versions table; chunk_hashes array per version; 30-day retention default | Plus: snapshot-based history (full copy at key milestones, delta-only between); intelligent version pruning (keep all versions in last 7 days, hourly in last 30 days, daily after) |
| Client state machine | 6 states: SYNCED, MODIFIED_LOCAL, UPLOADING, MODIFIED_REMOTE, DOWNLOADING, CONFLICT | Plus: PAUSED state (user manually stops sync); SELECTIVE_SYNC (some folders excluded); offline-first design (client always reads local copy, background sync catches up) |

---

## Additional Exercises

### Exercise 6: Resumable Upload with Chunk-Level Recovery

**Problem:** A user is uploading a 2 GB video file (512 chunks of 4 MB each). After uploading 400 chunks, their WiFi drops. When they reconnect, design the system to resume from chunk 401, not restart from the beginning.

**Solution:**

```python
# Upload session schema in Redis:
# Key: upload_session:{session_id}
# Type: HASH
# Fields: file_id, user_id, total_chunks, filename, created_at
# TTL: 24 hours

# Chunk tracking:
# Key: upload_session:{session_id}:received_chunks
# Type: SET (each received chunk_index is a member)

# Step 1: Create upload session
def create_upload_session(user_id, filename, total_chunks):
    session_id = UUID.generate()
    redis.hset(f"upload_session:{session_id}", {
        "file_id": UUID.generate(),
        "user_id": user_id,
        "filename": filename,
        "total_chunks": total_chunks,
        "created_at": time.time()
    })
    redis.expire(f"upload_session:{session_id}", 86400)
    return session_id

# Step 2: Upload a chunk
def upload_chunk(session_id, chunk_index, chunk_data):
    chunk_hash = sha256(chunk_data)
    
    # Upload to S3 (idempotent — same hash goes to same key)
    s3.put(key=f"chunks/{chunk_hash}", body=chunk_data)
    
    # Record as received
    redis.sadd(f"upload_session:{session_id}:received_chunks", f"{chunk_index}:{chunk_hash}")
    redis.expire(f"upload_session:{session_id}:received_chunks", 86400)
    
    return {"chunk_index": chunk_index, "hash": chunk_hash, "status": "received"}

# Step 3: Client drops connection after 400 chunks. Reconnects.
def get_upload_status(session_id):
    total = int(redis.hget(f"upload_session:{session_id}", "total_chunks"))
    received = redis.smembers(f"upload_session:{session_id}:received_chunks")
    received_indices = {int(r.split(":")[0]) for r in received}
    missing = [i for i in range(total) if i not in received_indices]
    return {"received_count": len(received), "missing_chunks": missing}

# Client receives: {"received_count": 400, "missing_chunks": [400, 401, ..., 511]}
# Client uploads only chunks 400–511. No restart from chunk 0.

# Step 4: Finalize when all chunks received
def finalize_upload(session_id):
    session = redis.hgetall(f"upload_session:{session_id}")
    total = int(session["total_chunks"])
    received = redis.smembers(f"upload_session:{session_id}:received_chunks")
    
    if len(received) < total:
        return {"error": f"Missing {total - len(received)} chunks"}
    
    # Build ordered chunk list
    chunk_list = sorted(received, key=lambda x: int(x.split(":")[0]))
    chunk_hashes = [c.split(":")[1] for c in chunk_list]
    
    # Write file record to DB
    db.insert("files", {
        "file_id": session["file_id"],
        "owner_user_id": session["user_id"],
        "filename": session["filename"],
        "chunk_hashes": chunk_hashes,
        "created_at": NOW()
    })
    
    # Cleanup Redis session
    redis.delete(f"upload_session:{session_id}")
    redis.delete(f"upload_session:{session_id}:received_chunks")
    
    return {"status": "complete", "file_id": session["file_id"]}
```

---

### Exercise 7: Detecting File Corruption at Download

**Problem:** A file is stored as 256 chunks, each with a SHA-256 hash in the metadata. When a user downloads the file, how do you detect and recover from chunk corruption in S3?

**Solution:**

```python
def download_file(file_id, user_id):
    # Step 1: Fetch metadata
    file_record = db.query("SELECT chunk_hashes FROM files WHERE file_id=?", [file_id])
    chunk_hashes = file_record["chunk_hashes"]  # ordered list of expected hashes
    
    corrupted_chunks = []
    file_data = bytearray()
    
    for i, expected_hash in enumerate(chunk_hashes):
        # Step 2: Download chunk from S3 (content-addressed key)
        chunk_data = s3.get(key=f"chunks/{expected_hash}")
        
        # Step 3: Verify integrity
        actual_hash = sha256(chunk_data)
        if actual_hash != expected_hash:
            # Chunk corrupted in S3!
            corrupted_chunks.append(i)
            
            # Step 4: Try alternate S3 region (replication target)
            chunk_data = s3_replica.get(key=f"chunks/{expected_hash}")
            actual_hash = sha256(chunk_data)
            
            if actual_hash != expected_hash:
                # Both regions corrupted — irrecoverable
                raise ChunkCorruptionError(f"Chunk {i} corrupted in all replicas")
        
        file_data.extend(chunk_data)
    
    if corrupted_chunks:
        # Log for S3 repair job (re-copy from replica)
        repair_queue.publish({"chunks": [chunk_hashes[i] for i in corrupted_chunks]})
    
    return bytes(file_data)

# S3 provides 11 nines of durability (probability of losing data: 1 in 100 billion per year)
# Corruption is far more likely than loss — always verify SHA-256 at download time
# This verification adds < 1ms per chunk (SHA-256 of 4MB chunk: ~2ms on modern CPU)
```

---

### Exercise 8: Shared Folder with Permissions Model

**Problem:** Alice creates a shared folder with 3 permissions levels: View (can download), Edit (can upload), Admin (can add/remove members). Design the permissions check for each file operation.

**Solution:**

```sql
-- Schema
CREATE TABLE folder_members (
  folder_id   UUID,
  user_id     BIGINT,
  role        VARCHAR(10),  -- 'view', 'edit', 'admin'
  added_at    TIMESTAMP,
  added_by    BIGINT,       -- user who added this member
  PRIMARY KEY (folder_id, user_id)
);

-- Permission check middleware (runs before every file operation)
def check_permission(user_id, folder_id, required_role):
    # Cache in Redis for 5 minutes (permission changes are rare)
    cache_key = f"perm:{folder_id}:{user_id}"
    cached_role = redis.get(cache_key)
    
    if cached_role is None:
        row = db.query("""
            SELECT role FROM folder_members
            WHERE folder_id=? AND user_id=?
        """, [folder_id, user_id])
        cached_role = row["role"] if row else "none"
        redis.set(cache_key, cached_role, ex=300)
    
    role_levels = {"none": 0, "view": 1, "edit": 2, "admin": 3}
    return role_levels.get(cached_role, 0) >= role_levels[required_role]

-- Permission matrix:
-- Operation          Required role
-- download_file      view
-- upload_file        edit
-- delete_file        edit (own files) / admin (others' files)
-- add_member         admin
-- remove_member      admin
-- rename_folder      admin
-- transfer_ownership admin (owner only)

-- On permission change: invalidate cache
def change_member_role(folder_id, target_user_id, new_role, requestor_id):
    # Verify requestor is admin
    if not check_permission(requestor_id, folder_id, "admin"):
        raise PermissionDenied
    
    db.update("folder_members", {"role": new_role},
              {"folder_id": folder_id, "user_id": target_user_id})
    
    # Invalidate cached permission
    redis.delete(f"perm:{folder_id}:{target_user_id}")
```

---

## Key Interview Signals — What L5 Looks Like In the Room

**Signal 1: You identify the three separate problems without prompting.**
File sync has three independent hard problems: (1) delta transfer efficiency (chunking + dedup), (2) multi-device conflict resolution (version vectors + keep-both), (3) reliable notification delivery (WebSocket push + cursor-based pull fallback). Weak candidates design a single monolithic "sync service." L5 candidates decompose the problem and address each piece with the right tool.

**Signal 2: You explain why the chunk boundary matters.**
When asked about chunking, the L5 answer is not "split into 4 MB pieces." It's "fixed 4 MB chunks have a boundary shift problem — inserting 1 byte at the beginning shifts all chunk boundaries, forcing a full re-upload. Rabin fingerprinting solves this with content-based boundaries that resynchronize after an edit." Knowing the flaw of the simpler approach and when you'd pay the complexity cost of the better approach is an L5 signal.

**Signal 3: You distinguish "reliable" from "fast" in notification design.**
Push notifications are fast but unreliable (the device might be offline). Cursor-based polling is reliable but slow. The L5 design uses both: push for latency, pull for correctness. If you only describe push, the interviewer will ask "what happens when the device is offline?" and you've demonstrated you hadn't thought about the failure mode.

**Signal 4: You address storage cost without being asked.**
The deduplication story is not just about bandwidth (delta sync) — it's also about storage. If a 4 MB image is uploaded by 10,000 users, only 1 copy is stored in S3 (content-addressed, key = SHA-256). The L5 candidate mentions this and the privacy implication (cross-user dedup leaks chunk existence) and the fix (confirm chunk existence only for that user's prior uploads). This shows you understand the second-order consequences of design decisions.
