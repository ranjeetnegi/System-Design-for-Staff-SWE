# Chapter 61g: File Sync Service — Dropbox / Google Drive

> Dropbox's core promise is: edit a file on your laptop, and it appears on
> your phone in seconds. The hard part isn't storage — it's detecting what
> changed, sending only the difference, and handling conflicts when two
> devices edit the same file offline.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

File sync is frequently asked at companies building collaboration tools (Dropbox,
Google Drive, Box, OneDrive, Notion). It is distinct from Ch52 (Object Storage),
which covers the storage API (S3-like PUT/GET). This chapter covers the sync
protocol: how clients detect changes, send deltas, and stay consistent across
devices. The key concepts — chunking, delta sync, conflict resolution — appear
across many distributed system problems.

---

## Planned Content

### Part 1: Requirements and Scale
- Upload a file → available on all user's devices within 30 seconds
- Functional: upload, download, sync across devices, share with others, view history
- Non-functional: < 30s sync latency, deduplicate identical files/chunks, handle offline edits
- Scale: 500M users, 50M DAU, 10B files stored, 1B file updates/day
- Not in scope: real-time collaborative editing (that's Ch65 — Google Docs); this is file-level sync

### Part 2: Why You Can't Just Re-upload the Whole File
- A 1GB video file changes by 1 sentence in the embedded subtitle — uploading 1GB is wasteful
- Delta sync: only upload the changed parts
- Chunking: split each file into 4MB chunks; compute SHA-256 hash of each chunk
- On update: compare chunk hashes — only upload chunks whose hash changed
- Deduplication: two users uploading the same file → only one copy stored (content-addressed storage)
- Bandwidth savings: typically 80–90% reduction vs. full re-upload for small edits

### Part 3: The Sync Protocol
- Client watches the local file system for changes (inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows)
- On change detected:
  1. Split file into 4MB chunks
  2. Compute SHA-256 hash per chunk
  3. Ask server: "which of these chunk hashes do you already have?"
  4. Upload only the missing chunks
  5. Send metadata update: file path, chunk list in order, modified timestamp
- Server reconstructs the file from chunks on download request
- Pull model (alternative): server sends a long-poll notification → client pulls the diff

### Part 4: Storage Architecture
- Chunk store: object storage (S3-like) — content-addressed by SHA-256 hash
  - Key = SHA-256 of chunk content; value = chunk bytes
  - Dedup is automatic: identical chunks share one storage object
- Metadata store: relational DB — file_id, user_id, path, chunk_list (ordered), version, modified_at
- Chunk references: file_metadata table stores ordered list of chunk hashes
- On download: fetch chunk list from metadata DB → fetch each chunk from chunk store → reassemble

### Part 5: Conflict Resolution
- Conflict scenario: user edits file on laptop (offline), edits same file on phone (also offline), both come online
- Detection: version vector or last-modified timestamp comparison
- Resolution strategy (Dropbox approach): keep both versions
  - Original file: "report.docx"
  - Conflicted copy: "report (Jane's conflicted copy 2024-01-15).docx"
  - User resolves manually
- Alternative: last-write-wins (timestamp) — simpler but loses one version silently
- Operational transform / CRDT: for real-time collaborative editing (out of scope here)

### Part 6: Notification and Push Sync
- When user A updates a file shared with user B, how does B's client know to sync?
- Long polling: client holds an open HTTP request; server responds when there's an update
- WebSocket: persistent connection; server pushes "file updated" event to all connected devices
- Push notification: for mobile devices that aren't actively connected (APNs / FCM)
- Event payload: {file_id, version, modified_by} — client then fetches the diff

### Part 7: System Architecture
- Client app: file watcher → chunk splitter → sync client → uploads chunks + metadata
- Upload service: receives chunks → stores in S3 → updates metadata DB → publishes event to queue
- Notification service: consumes event → pushes to all user's connected devices via WebSocket
- Metadata service: CRUD for file metadata; version history; sharing permissions
- Chunk store: S3-compatible object storage
- Metadata DB: Postgres (with file tree structure) + Redis (online device registry)

### Part 8: Interview Framework
- Start by distinguishing from object storage (Ch52): "This is about the sync protocol, not just storage"
- Explain chunking before anything else — it's the insight the question tests
- Walk the full flow: change detected → chunk → diff → upload → notify other devices
- Cover conflict resolution — interviewers always ask about offline edits
- L5 bar: chunking, delta sync, dedup, notification flow, conflict handling
- L6 bar: sharding the metadata DB, bandwidth optimization across regions,
  resumable uploads (handle interrupted large file uploads), client versioning

---

## The One-Sentence Summary

> "File sync = split file into 4MB chunks (SHA-256 hash per chunk) + delta sync (only upload changed chunks) + content-addressed chunk store (identical chunks stored once) + metadata DB (ordered chunk list per version) + WebSocket notification to push sync to other devices — the core insight is that sending the whole file every time is wasteful; chunking lets you send only what changed."

---

*Full chapter: ~2,500 lines. Section 5 — L5 / Senior SWE. Distinct from Ch52 (object storage API).*
